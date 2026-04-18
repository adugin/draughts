"""EngineSession — stateful engine protocol session.

Each session owns:
  - an AIEngine instance (one per side that moves, or one that we keep
    resetting for single-side use)
  - a HeadlessGame tracking the current position
  - option values (Level, MoveTime, Hash, Threads)

The session is driven by EngineSession.run(input, output) which reads
lines from *input*, dispatches commands, and writes responses to *output*.

Threading model
---------------
``go depth N`` and ``go movetime MS`` run the search *synchronously* in
the main loop — the search will finish on its own.

``go infinite`` spawns a worker thread.  The main thread keeps reading
stdin for a ``stop`` command.  On ``stop``, the worker's deadline is set
to the past so the cooperative cancel in _alphabeta fires.  The worker
then returns its best move and the session emits ``bestmove``.
"""

from __future__ import annotations

import threading
import time
from typing import IO

from draughts.config import Color
from draughts.game.ai import AIMove
from draughts.game.ai.search import _search_best_move
from draughts.game.ai.state import SearchContext
from draughts.game.board import Board
from draughts.game.fen import START_FEN, parse_fen
from draughts.game.headless import HeadlessGame

from .protocol import emit, format_move, parse_command, parse_move

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_LEVEL = 4
_DEFAULT_MOVE_TIME_MS = 3000
_MAX_INFINITE_DEPTH = 20  # iterative deepening cap for "go infinite"


# ---------------------------------------------------------------------------
# EngineSession
# ---------------------------------------------------------------------------


class EngineSession:
    """One interactive session with the engine protocol.

    Instantiate, then call ``run(input_stream, output_stream)``.  For tests
    you can drive individual commands via ``handle_line(line, output)``.
    """

    def __init__(self) -> None:
        self._level: int = _DEFAULT_LEVEL
        self._move_time_ms: int = _DEFAULT_MOVE_TIME_MS

        # Current game / position state.  None until first 'position' command.
        self._game: HeadlessGame | None = None
        self._turn: Color = Color.WHITE  # side to move in current position

        # Dedicated SearchContext for the session engine — owns its own TT.
        self._ctx: SearchContext = SearchContext()

        # For "go infinite" threading
        self._stop_event: threading.Event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        # Flag: has the session received 'quit'?
        self._quit: bool = False

    # -----------------------------------------------------------------------
    # Public: run the main loop
    # -----------------------------------------------------------------------

    def run(self, input_stream: IO[str], output_stream: IO[str]) -> None:
        """Read-dispatch-respond loop.  Returns when 'quit' is received or
        the input stream is exhausted."""
        while not self._quit:
            try:
                line = input_stream.readline()
            except (EOFError, OSError):
                break
            if line == "":
                # EOF
                break
            self.handle_line(line, output_stream)

    def handle_line(self, line: str, out: IO[str]) -> None:
        """Dispatch one protocol line.  Public so tests can call directly."""
        cmd, tokens = parse_command(line)
        if not cmd:
            return

        if cmd in ("uci", "udri"):
            self._cmd_uci(out)
        elif cmd == "isready":
            emit(out, "readyok")
        elif cmd == "setoption":
            self._cmd_setoption(tokens, out)
        elif cmd == "newgame":
            self._cmd_newgame(out)
        elif cmd == "position":
            self._cmd_position(tokens, out)
        elif cmd == "go":
            self._cmd_go(tokens, out)
        elif cmd == "stop":
            self._cmd_stop(out)
        elif cmd == "quit":
            self._quit = True
        else:
            # Unknown command — silently ignore (protocol spec)
            pass

    # -----------------------------------------------------------------------
    # Command handlers
    # -----------------------------------------------------------------------

    def _cmd_uci(self, out: IO[str]) -> None:
        import draughts

        emit(out, f"id name DRAUGHTS-engine v{draughts.__version__}")
        emit(out, f"id author {draughts.__author__}")
        emit(out, "option name Hash type spin default 64 min 1 max 1024")
        emit(out, "option name Threads type spin default 1 min 1 max 1")
        emit(out, "option name Level type spin default 4 min 1 max 6")
        emit(out, "option name MoveTime type spin default 3000 min 100 max 60000")
        emit(out, "udriok")

    def _cmd_newgame(self, out: IO[str]) -> None:
        """Reset the session to a fresh state."""
        self._game = None
        self._ctx.clear()

    def _cmd_setoption(self, tokens: list[str], out: IO[str]) -> None:
        """setoption name <K> value <V>"""
        # Normalise: collect tokens around 'name' and 'value' keywords
        # Format: name <K> value <V>  — standard UCI layout
        try:
            name_idx = [t.lower() for t in tokens].index("name")
        except ValueError:
            return  # malformed — ignore

        # Everything between 'name' and 'value' is the option name
        try:
            value_idx = [t.lower() for t in tokens].index("value")
        except ValueError:
            return  # missing value — ignore

        key = " ".join(tokens[name_idx + 1 : value_idx]).strip()
        val_str = " ".join(tokens[value_idx + 1 :]).strip()

        if key.lower() == "level":
            try:
                level = int(val_str)
                self._level = max(1, min(6, level))
            except ValueError:
                pass
        elif key.lower() == "movetime":
            try:
                ms = int(val_str)
                self._move_time_ms = max(100, min(60000, ms))
            except ValueError:
                pass
        elif key.lower() == "hash":
            # Stub — transposition table size is not dynamically resizable yet
            emit(out, "info string Hash option not implemented (stub)")
        elif key.lower() == "threads":
            # Stub — SMP not yet implemented
            emit(out, "info string Threads option not implemented (stub)")
        # Unknown options are silently ignored

    def _cmd_position(self, tokens: list[str], out: IO[str]) -> None:
        """position startpos [moves m1 m2 ...]
        position fen <FEN> [moves m1 m2 ...]
        """
        if not tokens:
            return

        idx = 0
        pos_type = tokens[idx].lower()
        idx += 1

        # Parse the base position
        if pos_type == "startpos":
            board, color = parse_fen(START_FEN)
        elif pos_type == "fen":
            # Collect FEN tokens until we hit 'moves' or end
            fen_parts: list[str] = []
            while idx < len(tokens) and tokens[idx].lower() != "moves":
                fen_parts.append(tokens[idx])
                idx += 1
            fen_str = " ".join(fen_parts)
            try:
                board, color = parse_fen(fen_str)
            except ValueError as exc:
                emit(out, f"info string FEN parse error: {exc}")
                return
        else:
            emit(out, f"info string Unknown position type: {pos_type!r}")
            return

        # Build a HeadlessGame from this position
        pos_str = _board_to_position_string(board)
        self._game = HeadlessGame(
            difficulty=self._level,
            position=pos_str,
            auto_ai=False,
        )
        self._game._turn = color
        self._turn = color

        # Apply move list if present
        if idx < len(tokens) and tokens[idx].lower() == "moves":
            idx += 1
            for move_token in tokens[idx:]:
                self._apply_move_to_game(move_token, out)

    def _apply_move_to_game(self, token: str, out: IO[str]) -> None:
        """Parse and apply one algebraic move token to self._game."""
        if self._game is None:
            return
        try:
            kind, path = parse_move(token)
        except ValueError as exc:
            emit(out, f"info string Bad move token {token!r}: {exc}")
            return

        if kind == "capture":
            record = self._game.make_capture(path)
        else:
            if len(path) < 2:
                emit(out, f"info string Move {token!r} has no destination")
                return
            record = self._game.make_move(path[0], path[1])

        if record is None:
            emit(out, f"info string Illegal move {token!r}")
        else:
            self._turn = self._game.turn

    def _cmd_go(self, tokens: list[str], out: IO[str]) -> None:
        """go depth N | go movetime MS | go infinite"""
        if not tokens:
            # Default: use level-based movetime
            self._go_movetime(self._move_time_ms, out)
            return

        mode = tokens[0].lower()

        if mode == "depth":
            try:
                depth = int(tokens[1]) if len(tokens) > 1 else 4
            except (ValueError, IndexError):
                depth = 4
            depth = max(1, depth)  # clamp: depth 0 would produce no move (BUG-007)
            self._go_depth(depth, out)

        elif mode == "movetime":
            try:
                ms = int(tokens[1]) if len(tokens) > 1 else self._move_time_ms
            except (ValueError, IndexError):
                ms = self._move_time_ms
            self._go_movetime(ms, out)

        elif mode == "infinite":
            self._go_infinite(out)

        else:
            # Unknown go sub-command — fall back to default movetime
            self._go_movetime(self._move_time_ms, out)

    def _cmd_stop(self, out: IO[str]) -> None:
        """Request the running infinite search to terminate."""
        self._stop_event.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

    # -----------------------------------------------------------------------
    # Search launchers
    # -----------------------------------------------------------------------

    def _go_depth(self, depth: int, out: IO[str]) -> None:
        """Run iterative deepening to a fixed depth, emitting info per depth."""
        board, color = self._current_board_and_color()
        if board is None:
            emit(out, "info string No position set")
            emit(out, "bestmove (none)")
            return

        self._ctx.clear()
        t0 = time.perf_counter()

        best_move: AIMove | None = None
        for d in range(1, depth + 1):
            move = _search_best_move(board, color, d, ctx=self._ctx)
            if move is None:
                break
            best_move = move
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            score_cp = int(self._ctx.last_score * 100)
            nodes = len(self._ctx.tt)
            nps = int(nodes / max(0.001, elapsed_ms / 1000))
            pv = format_move(move.kind, move.path)
            emit(
                out,
                f"info depth {d} score cp {score_cp} nodes {nodes} nps {nps} time {elapsed_ms} pv {pv}",
            )

        if best_move is None:
            emit(out, "bestmove (none)")
        else:
            emit(out, f"bestmove {format_move(best_move.kind, best_move.path)}")

    def _go_movetime(self, time_ms: int, out: IO[str]) -> None:
        """Run time-limited iterative deepening."""
        board, color = self._current_board_and_color()
        if board is None:
            emit(out, "info string No position set")
            emit(out, "bestmove (none)")
            return

        self._ctx.clear()
        t0 = time.perf_counter()
        deadline = t0 + time_ms / 1000.0

        best_move: AIMove | None = None
        for d in range(1, _MAX_INFINITE_DEPTH + 1):
            move = _search_best_move(board, color, d, deadline=deadline, ctx=self._ctx)
            if move is None:
                break
            best_move = move
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            score_cp = int(self._ctx.last_score * 100)
            nodes = len(self._ctx.tt)
            nps = int(nodes / max(0.001, elapsed_ms / 1000))
            pv = format_move(move.kind, move.path)
            emit(
                out,
                f"info depth {d} score cp {score_cp} nodes {nodes} nps {nps} time {elapsed_ms} pv {pv}",
            )
            # Stop if deadline already past (search returned early due to cancel)
            if time.perf_counter() >= deadline:
                break

        if best_move is None:
            emit(out, "bestmove (none)")
        else:
            emit(out, f"bestmove {format_move(best_move.kind, best_move.path)}")

    def _go_infinite(self, out: IO[str]) -> None:
        """Start an infinite search in a worker thread without blocking stdin.

        The worker runs iterative deepening up to ``_MAX_INFINITE_DEPTH`` (or
        until ``stop`` sets ``_stop_event``).  It emits ``info`` lines and the
        final ``bestmove`` itself so that the main ``run()`` loop stays free to
        read the ``stop`` command from stdin.

        Note: on Windows ``select()`` cannot poll stdin, so true mid-search
        interruption requires sending ``stop`` before the search reaches max
        depth.  The worker is a daemon thread — if the process exits it will
        be killed automatically.
        """
        board, color = self._current_board_and_color()
        if board is None:
            emit(out, "info string No position set")
            emit(out, "bestmove (none)")
            return

        self._stop_event.clear()
        self._ctx.clear()

        def worker() -> None:
            t0 = time.perf_counter()
            local_ctx = self._ctx
            best: AIMove | None = None

            for d in range(1, _MAX_INFINITE_DEPTH + 1):
                if self._stop_event.is_set():
                    break
                move = _search_best_move(board, color, d, ctx=local_ctx)
                if move is None:
                    break
                best = move
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                score_cp = int(local_ctx.last_score * 100)
                nodes = len(local_ctx.tt)
                nps = int(nodes / max(0.001, elapsed_ms / 1000))
                pv = format_move(move.kind, move.path)
                emit(
                    out,
                    f"info depth {d} score cp {score_cp} nodes {nodes} nps {nps} time {elapsed_ms} pv {pv}",
                )
                if self._stop_event.is_set():
                    break

            # Emit bestmove from the worker so the main thread is not blocked
            if best is None:
                emit(out, "bestmove (none)")
            else:
                emit(out, f"bestmove {format_move(best.kind, best.path)}")
            # Signal that the worker has finished so _cmd_stop can clean up
            self._worker_thread = None

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()
        # Return immediately — run() loop continues reading stdin for 'stop'

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _current_board_and_color(self) -> tuple[Board | None, Color]:
        """Return the current board + side-to-move.

        If no position has been set, creates a default start position.
        """
        if self._game is None:
            board, color = parse_fen(START_FEN)
            pos_str = _board_to_position_string(board)
            self._game = HeadlessGame(
                difficulty=self._level,
                position=pos_str,
                auto_ai=False,
            )
            self._game._turn = color
            self._turn = color

        return self._game.board, self._game.turn

    @property
    def level(self) -> int:
        return self._level

    @property
    def move_time_ms(self) -> int:
        return self._move_time_ms


# ---------------------------------------------------------------------------
# Utility: convert a Board to a position string (HeadlessGame ctor arg)
# ---------------------------------------------------------------------------


def _board_to_position_string(board: Board) -> str:
    """Convert a Board to the 32-char position string used by HeadlessGame."""
    return board.to_position_string()
