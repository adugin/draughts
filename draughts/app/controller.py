"""Game controller — ties together Board, AI, UI, and saves.

Central coordinator managing game state, turn logic, player input
validation, AI execution (in a worker thread), and save/load.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from draughts.config import AUTOSAVE_FILENAME, BOARD_SIZE, Color, GameSettings, get_data_dir, migrate_difficulty
from draughts.game.ai import AIEngine, AIMove
from draughts.game.board import Board
from draughts.game.pdn import PDNGame, load_pdn_file, write_pdn, xy_to_square
from draughts.game.save import GameSave, autosave, load_game, save_game

logger = logging.getLogger("draughts.controller")


# ---------------------------------------------------------------------------
# PDN move helpers (module-level, no Qt dependency)
# ---------------------------------------------------------------------------


def _infer_pdn_move_from_boards(before: Board, after: Board) -> str | None:
    """Infer a PDN numeric move token from two consecutive board states.

    Returns a string like '22-17' or '9x18' or None on failure.
    """
    import numpy as np

    diff = before.grid != after.grid
    changed_yx = list(zip(*np.where(diff), strict=False))
    if not changed_yx:
        return None

    sources = []
    dests = []
    for y, x in changed_yx:
        b_piece = int(before.grid[y, x])
        a_piece = int(after.grid[y, x])
        if b_piece != 0 and a_piece == 0:
            sources.append((int(x), int(y)))
        elif b_piece == 0 and a_piece != 0:
            dests.append((int(x), int(y)))
        elif b_piece != 0 and a_piece != 0 and abs(b_piece) != abs(a_piece):
            # King promotion in place — counts as a dest (source is same square)
            dests.append((int(x), int(y)))

    if len(sources) == 1 and len(dests) == 1:
        sx, sy = sources[0]
        tx, ty = dests[0]
        try:
            src_sq = xy_to_square(sx, sy)
            dst_sq = xy_to_square(tx, ty)
        except ValueError:
            return None
        is_capture = len(changed_yx) > 2
        sep = "x" if is_capture else "-"
        return f"{src_sq}{sep}{dst_sq}"

    return None


def _apply_pdn_move(board: Board, pdn_move: str) -> None:
    """Apply a PDN numeric move to a board in-place.

    Supports simple moves ('22-17'), single captures ('9x18'), and
    multi-jump captures ('9x18x27').
    Raises ValueError if the move cannot be applied.
    """
    from draughts.game.pdn import square_to_xy

    is_capture = "x" in pdn_move
    sep = "x" if is_capture else "-"
    parts = pdn_move.split(sep)
    squares = [square_to_xy(int(p.strip())) for p in parts]

    if not is_capture:
        if len(squares) != 2:
            raise ValueError(f"Invalid simple move: {pdn_move!r}")
        x1, y1 = squares[0]
        x2, y2 = squares[1]
        board.execute_move(x1, y1, x2, y2)
    else:
        # Build a full path for execute_capture_path
        board.execute_capture_path(squares)


class AIWorker(QObject):
    """Runs AI computation in a background thread."""

    finished = pyqtSignal(object, int)  # (AIMove | None, generation)

    def __init__(self, board: Board, engine: AIEngine, generation: int):
        super().__init__()
        self._board = board
        self._engine = engine
        self._generation = generation

    def run(self):
        try:
            result = self._engine.find_move(self._board.copy())
        except Exception:
            logger.exception("AI crashed during find_move")
            result = None
        self.finished.emit(result, self._generation)


class GameController(QObject):
    """Central game logic controller.

    Signals:
        board_changed: board was updated, UI should repaint
        turn_changed: whose turn it is now ('w' or 'b')
        game_over: (message) — game ended
        ai_thinking: (bool) — AI started/finished thinking
        selection_changed: (x, y) or (None, None) — piece selection changed
        capture_highlights_changed: list of (x, y) — multi-capture intermediate squares
    """

    board_changed = pyqtSignal()
    turn_changed = pyqtSignal(str)
    game_over = pyqtSignal(str)
    message_changed = pyqtSignal(str)
    ai_thinking = pyqtSignal(bool)
    selection_changed = pyqtSignal(object, object)
    capture_highlights_changed = pyqtSignal(list)
    capture_hint = pyqtSignal(list)  # [(x, y), ...] — pieces that must capture (pulse animation)
    last_move_changed = pyqtSignal(object)  # tuple[tuple,tuple] | None — last move highlight
    hint_ready = pyqtSignal(object, str)  # (squares: list[tuple], message: str) — D16 hint

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = Board()
        self.settings = GameSettings()

        # Game state
        self._current_turn: Color = Color.WHITE
        self._computer_color: Color = Color.BLACK
        self._player_color: Color = Color.WHITE
        self._selected: tuple[int, int] | None = None
        self._capture_path: list[tuple[int, int]] = []

        # History
        self._positions: list[str] = []
        self._replay_history: list[str] = []
        self._ply_count: int = 0
        self._game_started: bool = False
        self._position_counts: dict[str, int] = {}
        # Optional game tree carried along with the game — populated by
        # load_game_from_pdn so that re-export preserves variations and
        # annotations (M5.b). None means "no imported tree"; save then
        # falls back to inferring the main line from _positions.
        self._game_tree = None  # type: GameTree | None

        # Draw rule counters (FMJD)
        self._quiet_plies: int = 0  # plies without captures or pawn moves
        self._kings_only_plies: int = 0  # plies where all pieces are kings

        # AI thread
        self._ai_thread: QThread | None = None
        self._ai_worker: AIWorker | None = None
        # Pending (still-alive) AI threads/workers from prior generations that
        # were invalidated by flip_sides. Python refs are held here so neither
        # Qt nor GC collects them until their natural finish + deleteLater.
        self._pending_ai: list[tuple[QThread, AIWorker]] = []
        # Generation token — incremented when the in-flight AI result must
        # be discarded (flip sides). Stale workers emit against an old token
        # and _on_ai_finished silently ignores them.
        self._ai_generation: int = 0

        # Record initial position
        self._positions.append(self.board.to_position_string())
        self._replay_history.append(self.board.to_position_string())

    # --- New game ---

    def new_game(self):
        """Reset everything for a new game from the standard starting position."""
        self.new_game_from_position(Board(), Color.WHITE)

    def new_game_from_position(self, board: Board, turn: Color):
        """Reset everything for a new game from an arbitrary position.

        This is the single point of initialization for all game state.
        Both new_game() and the board editor "play from here" call this,
        ensuring no private field is forgotten.
        """
        self.board = board
        self._current_turn = turn
        self._computer_color = Color.BLACK if not self.settings.invert_color else Color.WHITE
        self._player_color = Color.WHITE if not self.settings.invert_color else Color.BLACK
        self._selected = None
        self._capture_path = []
        pos = board.to_position_string()
        self._positions = [pos]
        self._replay_history = [pos]
        self._ply_count = 0
        self._game_started = turn != Color.WHITE  # custom position = game already in progress
        self._position_counts = {pos: 1}
        self._quiet_plies = 0
        self._kings_only_plies = 0
        # Reset imported variation tree — a new game starts a fresh main
        # line with no variations (M5.b).
        self._game_tree = None
        # Bump generation so any in-flight AI worker from the previous game
        # is dropped when it finishes (BUG-10). NB: we do NOT clear
        # _pending_ai — Python refs keep stale workers alive until their
        # run() returns and the finished-handler's stale path cleans them.
        self._ai_generation += 1
        if self._ai_thread is not None and self._ai_worker is not None:
            self._pending_ai.append((self._ai_thread, self._ai_worker))
        self._ai_thread = None
        self._ai_worker = None

        self.last_move_changed.emit(None)
        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if turn == self._computer_color:
            self._start_computer_turn()

    # --- Player input ---

    def on_cell_left_click(self, x: int, y: int):
        """Handle left-click on board cell.

        Input model (matches lidraughts/CheckerBoard):
        - Click own piece → select it (clears any partial capture path)
        - Click empty square → try to move/capture there
        - Multi-capture disambiguation is automatic via _try_capture_move:
          if the click is an intermediate point, the path extends;
          if it's a final point, the capture executes.
        """
        if self._current_turn != self._player_color:
            return
        if self._ai_thread is not None:
            return

        piece = self.board.piece_at(x, y)

        if self._selected is None:
            if self._is_player_piece(piece):
                self._select_piece(x, y)
            return

        sx, sy = self._selected

        # Click on own piece → reselect (always allowed, even mid-capture)
        if self._is_player_piece(piece) and (x, y) != (sx, sy):
            self._select_piece(x, y)
            return

        # Click on empty square → try move or capture
        if piece == Board.EMPTY:
            self._try_move(sx, sy, x, y)

    def on_cell_right_click(self, x: int, y: int):
        """Right-click in game mode: deselect piece and clear capture path."""
        if self._selected is not None:
            self._selected = None
            self._capture_path = []
            self.selection_changed.emit(None, None)
            self.capture_highlights_changed.emit([])

    def _is_player_piece(self, piece: int) -> bool:
        is_player = self.board.is_white(piece) if self._player_color == Color.WHITE else self.board.is_black(piece)
        return bool(is_player)

    def _select_piece(self, x: int, y: int):
        """Select a piece for moving."""
        if self.board.has_any_capture(self._player_color):
            captures = self.board.get_captures(x, y)
            if not captures:
                if self.settings.remind:
                    self._find_and_signal_capture()
                return

        self._selected = (x, y)
        self._capture_path = []
        self.selection_changed.emit(x, y)
        self.capture_highlights_changed.emit([])

    def _find_and_signal_capture(self):
        """Find pieces that must capture and signal them with pulse animation."""
        must_capture = []
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                piece = self.board.piece_at(x, y)
                if self._is_player_piece(piece) and self.board.get_captures(x, y):
                    must_capture.append((x, y))
        if must_capture:
            notation = ", ".join(Board.pos_to_notation(x, y) for x, y in must_capture)
            self.message_changed.emit(
                f"{'Шашка' if len(must_capture) == 1 else 'Шашки'} {notation} {'должна' if len(must_capture) == 1 else 'должны'} бить!"
            )
            self.capture_hint.emit(must_capture)

    def _try_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try to execute a move from (sx, sy) to (tx, ty)."""
        if self.board.has_any_capture(self._player_color):
            self._try_capture_move(sx, sy, tx, ty)
        else:
            self._try_normal_move(sx, sy, tx, ty)

    def _try_normal_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a non-capture move."""
        valid_moves = self.board.get_valid_moves(sx, sy)
        if (tx, ty) not in valid_moves:
            return

        notation = f"{Board.pos_to_notation(sx, sy)}-{Board.pos_to_notation(tx, ty)}"
        self.board.execute_move(sx, sy, tx, ty)
        self._finish_player_move(notation, from_sq=(sx, sy), to_sq=(tx, ty), was_capture=False)

    def _try_capture_move(self, sx: int, sy: int, tx: int, ty: int):
        """Try a capture move."""
        full_path = [*self._capture_path, (tx, ty)] if self._capture_path else [(sx, sy), (tx, ty)]

        captures = self.board.get_captures(sx, sy)
        matching = [p for p in captures if p[: len(full_path)] == full_path and len(p) == len(full_path)]

        if not matching:
            partial = [p for p in captures if len(p) > len(full_path) and p[: len(full_path)] == full_path]
            if partial:
                if not self._capture_path:
                    self._capture_path = [(sx, sy), (tx, ty)]
                else:
                    self._capture_path.append((tx, ty))
                self.capture_highlights_changed.emit(self._capture_path[1:])
                return
            return

        best_path = matching[0]
        self.board.execute_capture_path(best_path)

        notation = ":".join(Board.pos_to_notation(x, y) for x, y in best_path)
        self._finish_player_move(notation, from_sq=best_path[0], to_sq=best_path[-1], was_capture=True)

    def _finish_player_move(
        self,
        notation: str,
        from_sq: tuple[int, int] | None = None,
        to_sq: tuple[int, int] | None = None,
        was_capture: bool = False,
    ):
        """Finalize player's move — record, switch turns, start AI."""
        self._ply_count += 1
        self._update_draw_counters(was_capture)
        self._game_started = True
        self._selected = None
        self._capture_path = []
        # Any new move makes an imported PDN tree stale — the game has
        # diverged from the loaded variation structure (M5.b).
        self._game_tree = None

        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)
        self._position_counts[pos] = self._position_counts.get(pos, 0) + 1

        if from_sq is not None and to_sq is not None:
            self.last_move_changed.emit((from_sq, to_sq))

        self.board_changed.emit()
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self._check_game_over():
            return

        self._do_autosave()

        self._current_turn = self._computer_color
        self.turn_changed.emit(self._current_turn)
        self._start_computer_turn()

    # --- Computer turn ---

    def _start_computer_turn(self):
        """Start the AI computation in a background thread.

        The worker carries the current generation token. If flip_sides()
        bumps the token before the worker finishes, its result is discarded
        in _on_ai_finished.
        """
        self.message_changed.emit("Думаю...")
        self.ai_thinking.emit(True)

        generation = self._ai_generation
        self._ai_thread = QThread()
        engine = AIEngine(
            difficulty=self.settings.difficulty,
            color=self._computer_color,
            search_depth=self.settings.search_depth,
            use_book=self.settings.use_opening_book,
            use_bitbase=self.settings.use_endgame_bitbase,
        )
        self._ai_worker = AIWorker(self.board, engine, generation)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_thread.start()

    def _on_ai_finished(self, result: AIMove | None, generation: int):
        """Handle AI computation result."""
        # Stale result (flip_sides was called while AI was thinking). Clean up
        # the stale thread here — don't touch self._ai_thread/_ai_worker which
        # may already point to a new worker started after the flip.
        if generation != self._ai_generation:
            logger.debug("Ignoring stale AI result (worker gen=%d, current=%d)", generation, self._ai_generation)
            # Look up the stale thread/worker from _pending_ai by stored
            # generation — authoritative source. self.sender() may return
            # None during C++-object teardown (M4), in which case without
            # this fallback the thread would leak and pending_ai would not
            # be drained for this generation.
            stale_entries = [(t, w) for (t, w) in self._pending_ai if w._generation == generation]
            for thread, worker in stale_entries:
                if thread is not None:
                    thread.quit()
                    thread.wait()
                if worker is not None:
                    worker.deleteLater()
                if thread is not None:
                    thread.deleteLater()
            # Remove from pending list. Compare by stored generation — relying
            # on identity (w is not worker) is unsafe because self.sender()
            # may return a different Python wrapper for the same C++ QObject
            # than the one originally stashed (BUG-6).
            self._pending_ai = [(t, w) for (t, w) in self._pending_ai if w._generation != generation]
            return
        try:
            self._on_ai_finished_inner(result)
        except Exception:
            logger.exception("CRASH in _on_ai_finished")

    def _on_ai_finished_inner(self, result: AIMove | None):
        self.ai_thinking.emit(False)
        self.message_changed.emit("")

        if self._ai_thread is not None:
            self._ai_thread.quit()
            self._ai_thread.wait()
            if self._ai_worker is not None:
                self._ai_worker.deleteLater()
            self._ai_thread.deleteLater()
            self._ai_worker = None
            self._ai_thread = None

        if result is None:
            self.game_over.emit("Вы выиграли!")
            return

        ai_from = result.path[0]
        ai_to = result.path[-1]

        if result.kind == "capture":
            self.board.execute_capture_path(result.path)
        elif result.kind in ("move", "sacrifice"):
            x1, y1 = result.path[0]
            x2, y2 = result.path[1]
            self.board.execute_move(x1, y1, x2, y2)
        else:
            logger.warning(f"Unknown AI move kind: {result.kind}")
            return

        self._ply_count += 1
        self._update_draw_counters(result.kind == "capture")

        pos = self.board.to_position_string()
        self._positions.append(pos)
        self._replay_history.append(pos)
        self._position_counts[pos] = self._position_counts.get(pos, 0) + 1

        self._current_turn = self._player_color

        self.last_move_changed.emit((ai_from, ai_to))
        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)

        if self._check_game_over():
            return

        self._do_autosave()

    # --- Resign ---

    def resign(self) -> None:
        """Resign the game on behalf of the player.

        Emits game_over with a loss message and invalidates any in-flight
        AI worker. Safe at any point — during AI thinking, mid-capture
        selection, or on the player's turn. No-op if the game is already
        over (Board.check_game_over returns non-None).
        """
        # Already over — ignore.
        if (
            self.board.check_game_over(
                self._position_counts,
                quiet_plies=self._quiet_plies,
                kings_only_plies=self._kings_only_plies,
            )
            is not None
        ):
            return

        # Invalidate any running AI worker via the generation token so its
        # move (if any) does not get applied to the post-resignation board.
        self._ai_generation += 1
        if self._ai_thread is not None and self._ai_worker is not None:
            self._pending_ai.append((self._ai_thread, self._ai_worker))
        self._ai_thread = None
        self._ai_worker = None

        # Clear transient UI state.
        self._selected = None
        self._capture_path = []

        self.ai_thinking.emit(False)
        self.message_changed.emit("")
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])
        self.game_over.emit("Вы сдались.")

    # --- Flip sides ---

    def flip_sides(self) -> None:
        """Swap player/computer colors in the middle of a game.

        Allowed only on the player's turn (D36). Pressing while AI is
        thinking is a no-op with a brief status hint — this prevents the
        spam scenario where repeated Ctrl+F makes the AI play both sides.
        After swap, the AI answers once (because _current_turn is now its
        color), and the next swap is blocked until AI finishes and control
        returns to the player.

        The board position, PDN-level move history, position counts, draw
        counters and ply count are absolute and remain untouched: the
        partition keeps playing from the same position with the same side
        to move. Only the role bindings ("which color does the human play")
        swap.

        No-op when the game is over.
        """
        if (
            self.board.check_game_over(
                self._position_counts,
                quiet_plies=self._quiet_plies,
                kings_only_plies=self._kings_only_plies,
            )
            is not None
        ):
            return

        # Guard (D36): only on the player's turn. Prevents swap-spam from
        # turning the game into AI-vs-AI.
        if self._current_turn != self._player_color:
            self.message_changed.emit("Дождитесь хода AI")
            return

        # Guard (BUG-5): block while the player is mid multi-capture selection.
        # The partial path would be silently dropped otherwise — confusing UX.
        if self._capture_path:
            self.message_changed.emit("Сначала завершите взятие")
            return

        # Invalidate any in-flight AI worker. Its result will be dropped by
        # _on_ai_finished via generation mismatch. Stash Python refs in
        # _pending_ai so neither Qt nor Python GC collects them until the
        # stale worker finishes and the finished-handler cleans up.
        self._ai_generation += 1
        if self._ai_thread is not None and self._ai_worker is not None:
            self._pending_ai.append((self._ai_thread, self._ai_worker))
        self._ai_thread = None
        self._ai_worker = None

        # Swap role bindings. _current_turn (absolute side-to-move) is untouched.
        self._player_color, self._computer_color = self._computer_color, self._player_color
        self.settings.invert_color = self._player_color == Color.BLACK

        # Clear UI state tied to the former player.
        self._selected = None
        self._capture_path = []

        self.ai_thinking.emit(False)
        self.message_changed.emit("")
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])
        self.last_move_changed.emit(None)
        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)

        # Persist new invert_color via autosave so --resume is consistent
        # with the user's current orientation (BUG-9).
        self._do_autosave()

        if self._current_turn == self._computer_color:
            self._start_computer_turn()

    # --- Undo ---

    def undo_move(self):
        """Undo the last move pair (player + computer). Available at all levels (D17).

        Normally undoes 2 plies (player move + AI response). If only 1 ply
        has been played (player moved but AI hasn't responded, or a game
        started from the editor), undoes that single ply.
        """
        if self._ply_count < 1:
            return
        if self._ai_thread is not None:
            return

        # Undo 2 plies (player + AI) when possible, otherwise 1
        undo_count = 2 if self._ply_count >= 2 else 1
        self._ply_count -= undo_count
        # Decrement position counts for the two undone positions
        for pos in self._positions[self._ply_count + 1 :]:
            cnt = self._position_counts.get(pos, 1)
            if cnt <= 1:
                self._position_counts.pop(pos, None)
            else:
                self._position_counts[pos] = cnt - 1
        if len(self._positions) > self._ply_count + 1:
            self._positions = self._positions[: self._ply_count + 1]
        if len(self._replay_history) > self._ply_count + 1:
            self._replay_history = self._replay_history[: self._ply_count + 1]

        self.board.load_from_position_string(self._positions[-1])

        self._selected = None
        self._capture_path = []
        self._current_turn = self._player_color
        # Undo invalidates any loaded PDN variation tree: the game now
        # diverges from the original main line, so re-emitting the tree
        # on save would produce a stale/incorrect RAV. Drop it — save
        # will fall back to the linear move history.
        self._game_tree = None

        self.last_move_changed.emit(None)
        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

    # --- Draw counters (FMJD endgame rules) ---

    def _update_draw_counters(self, was_capture: bool) -> None:
        """Update quiet-move and kings-only counters after a half-move."""
        import numpy as np

        grid = self.board.grid
        has_pawns = bool(np.any(np.abs(grid[grid != 0]) == 1))

        # Quiet plies: reset on capture or pawn presence change
        if was_capture or has_pawns:
            self._quiet_plies = 0 if was_capture else self._quiet_plies + 1
        else:
            self._quiet_plies += 1

        # Kings-only plies: count consecutive plies where all pieces are kings
        if has_pawns:
            self._kings_only_plies = 0
        else:
            self._kings_only_plies += 1

    # --- Game over ---

    _DRAW_MESSAGES: ClassVar[dict[str, str]] = {
        "draw_repetition": "Ничья — троекратное повторение позиции.",
        "draw_endgame": "Ничья — недостаточно материала.",
        "draw_kings_only": "Ничья — 15 ходов только дамками без взятий.",
        "draw_no_progress": "Ничья — 30 ходов без взятий и движения шашек.",
    }

    def _check_game_over(self) -> bool:
        """Check if the game is over. Emit game_over signal if so.

        Delegates to Board.check_game_over() — the single source of truth
        for game-over rules shared with HeadlessGame.
        """
        result = self.board.check_game_over(
            self._position_counts,
            quiet_plies=self._quiet_plies,
            kings_only_plies=self._kings_only_plies,
        )
        if result is None:
            return False

        winner, reason = result
        if winner is None:
            msg = self._DRAW_MESSAGES.get(reason, "Ничья.")
            self.game_over.emit(msg)
        elif winner == self._player_color:
            self.game_over.emit("Вы выиграли!")
        else:
            self.game_over.emit("Вы проиграли!")
        return True

    # --- Save / Load ---

    def save_current_game(self, filepath: str):
        """Save current game to file."""
        gs = GameSave(
            difficulty=self.settings.difficulty,
            speed=1,
            remind=self.settings.remind,
            sound_effect=False,
            pause=self.settings.pause,
            invert_color=self.settings.invert_color,
            positions=list(self._positions),
            replay_positions=list(self._replay_history),
        )
        save_game(filepath, gs)

    def load_saved_game(self, filepath: str):
        """Load a game from file."""
        gs = load_game(filepath)
        self.settings.difficulty = migrate_difficulty(gs.difficulty)
        self.settings.remind = gs.remind
        self.settings.pause = gs.pause
        self.settings.invert_color = gs.invert_color
        # Reconcile role bindings with the loaded invert_color flag (BUG-1).
        # Without this, a save made after flip_sides would resume with the
        # wrong player/computer color mapping.
        self._player_color = Color.BLACK if gs.invert_color else Color.WHITE
        self._computer_color = Color.WHITE if gs.invert_color else Color.BLACK

        # Invalidate any in-flight worker from the previous session (BUG-10).
        self._ai_generation += 1
        if self._ai_thread is not None and self._ai_worker is not None:
            self._pending_ai.append((self._ai_thread, self._ai_worker))
        self._ai_thread = None
        self._ai_worker = None

        self._positions = list(gs.positions)
        self._replay_history = list(gs.replay_positions) if gs.replay_positions else list(gs.positions)
        self._ply_count = len(self._positions) - 1

        if self._positions:
            self.board.load_from_position_string(self._positions[-1])
        else:
            self.board = Board()

        # Rebuild position counts from the loaded history so 3-fold
        # repetition detection works correctly for the loaded game.
        self._position_counts = {}
        for pos in self._positions:
            self._position_counts[pos] = self._position_counts.get(pos, 0) + 1

        self._current_turn = Color.WHITE if self._ply_count % 2 == 0 else Color.BLACK
        self._selected = None
        self._capture_path = []
        self._quiet_plies = 0
        self._kings_only_plies = 0
        self._game_started = self._ply_count > 0

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self._current_turn == self._computer_color:
            self._start_computer_turn()

    def save_game_as_pdn(self, filepath: str) -> None:
        """Save current game history as a PDN file.

        Reconstructs algebraic moves from consecutive board positions,
        converts to PDN numeric notation, and writes a single-game PDN file.
        Autosave is NOT affected — that stays JSON.
        """
        from draughts.game.pdn import RUSSIAN_DRAUGHTS_GAMETYPE, _today_date_str

        moves: list[str] = []
        for i in range(len(self._positions) - 1):
            board_before = Board()
            board_before.load_from_position_string(self._positions[i])
            board_after = Board()
            board_after.load_from_position_string(self._positions[i + 1])
            pdn_move = _infer_pdn_move_from_boards(board_before, board_after)
            if pdn_move:
                moves.append(pdn_move)

        # Determine result from last known position
        last_pos = self._positions[-1] if self._positions else ""
        has_black = "b" in last_pos or "B" in last_pos
        has_white = "w" in last_pos or "W" in last_pos
        if has_black and not has_white:
            result = "0-1"
        elif has_white and not has_black:
            result = "1-0"
        else:
            result = "*"

        game = PDNGame(
            headers={
                "Event": "?",
                "Site": "?",
                "Date": _today_date_str(),
                "Round": "?",
                "White": "?",
                "Black": "?",
                "Result": result,
                "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
            },
            moves=moves,
            # If this game was loaded from a PDN carrying variations/
            # annotations, write them back out (M5.b).
            tree=self._game_tree,
        )
        write_pdn([game], filepath)

    def load_game_from_pdn(self, filepath: str) -> None:
        """Load a game from a PDN file.

        Replays all moves from the first game in the file, reconstructing
        the position history. Starts the computer if it is its turn.
        """
        games = load_pdn_file(filepath)
        if not games:
            raise ValueError(f"No games found in PDN file: {filepath}")

        pdn_game = games[0]

        # Determine starting board (support SetUp/FEN positions)
        fen_str = pdn_game.headers.get("FEN")
        setup = pdn_game.headers.get("SetUp", "0")
        if setup == "1" and fen_str:
            from draughts.game.fen import parse_fen

            start_board, start_color = parse_fen(fen_str)
        else:
            start_board = Board()
            start_color = Color.WHITE

        # Replay moves to build position list
        positions: list[str] = [start_board.to_position_string()]
        board = start_board.copy()

        replay_truncated = False
        for pdn_move in pdn_game.moves:
            try:
                _apply_pdn_move(board, pdn_move)
                positions.append(board.to_position_string())
            except Exception:
                logger.warning(f"Could not apply PDN move {pdn_move!r}, stopping replay")
                replay_truncated = True
                break

        self._positions = positions
        self._replay_history = list(positions)
        self._ply_count = len(positions) - 1

        # Keep the variation tree so re-export via save_game_as_pdn
        # preserves alternatives, comments and NAGs — otherwise a load/
        # save round-trip would silently drop every non-main-line node.
        # But only when the main line replayed fully — a truncated replay
        # means our position no longer matches the tree's main line, so
        # re-emitting RAV would produce a broken PDN.
        self._game_tree = None if replay_truncated else pdn_game.tree

        # Rebuild position counts from replayed history so 3-fold
        # repetition detection works correctly for PDN-loaded games.
        self._position_counts = {}
        for pos in self._positions:
            self._position_counts[pos] = self._position_counts.get(pos, 0) + 1

        self.board.load_from_position_string(positions[-1])
        self._current_turn = start_color if self._ply_count % 2 == 0 else start_color.opponent
        self._selected = None
        self._capture_path = []
        self._quiet_plies = 0
        self._kings_only_plies = 0
        self._game_started = self._ply_count > 0

        self.board_changed.emit()
        self.turn_changed.emit(self._current_turn)
        self.selection_changed.emit(None, None)
        self.capture_highlights_changed.emit([])

        if self._current_turn == self._computer_color:
            self._start_computer_turn()

    def _do_autosave(self):
        """Auto-save current game state."""
        try:
            filepath = str(get_data_dir() / AUTOSAVE_FILENAME)
            gs = GameSave(
                difficulty=self.settings.difficulty,
                speed=1,
                remind=self.settings.remind,
                sound_effect=False,
                pause=self.settings.pause,
                invert_color=self.settings.invert_color,
                positions=list(self._positions),
                replay_positions=list(self._replay_history),
            )
            autosave(filepath, gs)
        except Exception:
            logger.warning("Autosave failed", exc_info=True)

    # --- Properties ---

    @property
    def current_turn(self) -> Color:
        return self._current_turn

    @property
    def player_color(self) -> Color:
        return self._player_color

    @property
    def computer_color(self) -> Color:
        return self._computer_color

    @property
    def replay_history(self) -> list[str]:
        return list(self._replay_history)

    @property
    def can_undo(self) -> bool:
        """Undo is available at all difficulty levels (D17)."""
        return self._ply_count >= 1

    @property
    def can_save(self) -> bool:
        return self._ply_count >= 1

    @property
    def is_thinking(self) -> bool:
        """True while the AI background thread is running."""
        return self._ai_thread is not None

    def get_hint(self) -> None:
        """Ask the engine for the best move + principal variation (M9).

        Ignored when it is not the player's turn, the game is over, or AI
        is already thinking.  Uses depth=6 for a richer PV; the first
        ply alone would be ~4-deep. Emits hint_ready(squares, message):
        ``squares`` = [from_sq, to_sq] of the recommended move for
        board highlighting; ``message`` shows the full PV (up to 4 moves
        ahead) with the final eval in pawns.
        """
        if self._current_turn != self._player_color:
            return
        if self._ai_thread is not None:
            return
        try:
            from draughts.game.analysis import compute_pv, get_ai_analysis
            from draughts.game.headless import HeadlessGame

            hg = HeadlessGame(position=self.board.to_position_string(), auto_ai=False)
            hg._turn = self._current_turn

            # Full analysis for the recommended move and its eval.
            analysis = get_ai_analysis(hg, depth=6)
            if analysis.best_move is None:
                return
            best = analysis.best_move
            from_sq = best.path[0]
            to_sq = best.path[-1]
            score = analysis.score
            score_str = f"{score:+.1f}"

            # Principal variation (up to 4 moves). Starts with ``best``;
            # we re-run it to keep a single, consistent code path in
            # compute_pv (including board-state mutations).
            pv = compute_pv(hg, depth=6, pv_length=4)
            pv_notations = [self._format_move_notation(mv) for mv in pv]
            if pv_notations:
                pv_text = " ".join(pv_notations)
                message = f"Лучший ход: {pv_text} (оценка: {score_str})"
            else:
                # Fallback: should not happen because analysis.best_move
                # was non-None, but guard just in case.
                from_note = self.board.pos_to_notation(*from_sq)
                to_note = self.board.pos_to_notation(*to_sq)
                sep = ":" if best.kind == "capture" else "-"
                message = f"Лучший ход: {from_note}{sep}{to_note} (оценка: {score_str})"

            self.hint_ready.emit([from_sq, to_sq], message)
        except Exception:
            logger.exception("get_hint failed")

    @staticmethod
    def _format_move_notation(mv) -> str:
        """Render an AIMove as readable algebraic notation (e.g. 'c3-d4', 'e5:c3:a5')."""
        sep = ":" if mv.kind == "capture" else "-"
        squares = [Board.pos_to_notation(x, y) for x, y in mv.path]
        if mv.kind == "capture":
            return sep.join(squares)
        return f"{squares[0]}{sep}{squares[-1]}"

    def get_book_moves(self) -> list[tuple[str, int, tuple[tuple[int, int], tuple[int, int]]]]:
        """Return opening-book moves for the current position (M9.b).

        Each entry is (notation, weight, (from_sq, to_sq)) where notation
        is like 'c3-d4' / 'e5:c3:a5', weight is the raw book weight
        (typically #games this move was played in our training set), and
        (from_sq, to_sq) are the internal (x, y) tuples of the first and
        last squares of the path for UI highlighting.

        Empty list if the position is not in the book, or the book is
        disabled, or no book is loaded.
        """
        if not self.settings.use_opening_book:
            return []
        from draughts.game.ai import DEFAULT_BOOK

        if DEFAULT_BOOK is None:
            return []
        moves_and_weights = DEFAULT_BOOK.probe_all(self.board, self._current_turn)
        result: list[tuple[str, int, tuple[tuple[int, int], tuple[int, int]]]] = []
        for ai_move, weight in moves_and_weights:
            notation = self._format_move_notation(ai_move)
            fx, fy = ai_move.path[0]
            tx, ty = ai_move.path[-1]
            from_sq: tuple[int, int] = (int(fx), int(fy))
            to_sq: tuple[int, int] = (int(tx), int(ty))
            result.append((notation, weight, (from_sq, to_sq)))
        return result

    def request_analysis(self, depth: int = 6) -> object:  # returns Analysis | None
        """Analyze the current position synchronously and return an Analysis.

        Delegates to draughts.game.analysis.get_ai_analysis() via a temporary
        HeadlessGame wrapper so the analysis uses an isolated SearchContext.
        This method is intended for use by the AnalysisPane which calls it
        in its own background QThread, so it must NOT be called from the
        main thread when a long-running analysis is acceptable.

        Returns None if the position cannot be analyzed (no board available).
        """
        try:
            from draughts.game.analysis import get_ai_analysis
            from draughts.game.headless import HeadlessGame

            hg = HeadlessGame(
                position=self.board.to_position_string(),
                auto_ai=False,
            )
            # Override the turn to match the current game state
            hg._turn = self._current_turn
            return get_ai_analysis(hg, depth=depth)
        except Exception:
            logger.exception("request_analysis failed")
            return None
