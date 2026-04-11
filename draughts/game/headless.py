"""Headless game engine — programmatic control without GUI.

Provides HeadlessGame for running complete games, analyzing positions,
and testing AI behavior without PyQt6 event loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from draughts.config import Color
from draughts.game import ai as _ai
from draughts.game.ai import (
    AIEngine,
    AIMove,
    _generate_all_moves,
    _search_best_move,
    adaptive_depth,
    evaluate_position,
)
from draughts.game.board import Board


@dataclass
class MoveRecord:
    """Record of a single move in the game."""

    ply: int  # 0-based ply number
    color: Color
    notation: str  # e.g. "c3-d4" or "f6:d4:b2"
    kind: str  # "move" or "capture"
    path: list[tuple[int, int]]
    eval_before: float  # evaluation before the move (from moving side)
    eval_after: float  # evaluation after the move (from moving side)


@dataclass
class GameResult:
    """Result of a completed game."""

    winner: Color | None  # None = draw
    # Possible values: "no_pieces", "no_moves", "draw_repetition",
    # "draw_max_ply", "draw_quiet", "timeout_game"
    reason: str
    ply_count: int
    moves: list[MoveRecord]
    final_position: str

    @property
    def result_string(self) -> str:
        if self.winner is None:
            return "1/2-1/2"
        return "1-0" if self.winner == Color.BLACK else "0-1"


@dataclass
class Analysis:
    """AI analysis of a position.

    Attributes:
        best_move: the minimax-chosen best move (or None if no legal moves).
        score: minimax score of the best move, from the side-to-move's
            perspective. This is the search result, NOT a static eval —
            matches what the AI actually sees and plays.
        static_score: the raw static eval of the current position, kept
            for debugging and comparison with `score`. A large gap
            between the two usually means horizon effects or a tactical
            sequence the search uncovered.
        depth: the effective search depth after adaptive_depth
            adjustment (may differ from the requested depth in crowded
            or endgame positions).
        legal_move_count: how many legal moves the side to move has.
    """

    best_move: AIMove | None
    score: float
    static_score: float
    depth: int
    legal_move_count: int


class HeadlessGame:
    """Complete game engine without GUI.

    Supports:
    - AI vs AI games
    - Manual moves with validation
    - Position analysis
    - Game recording and serialization
    """

    def __init__(
        self,
        difficulty: int = 2,
        depth: int = 0,
        black_engine: AIEngine | None = None,
        white_engine: AIEngine | None = None,
        position: str | None = None,
        auto_ai: bool = True,
    ):
        """Initialize a headless game.

        Args:
            difficulty: Default AI difficulty (1-3).
            depth: Default AI search depth (0=auto).
            black_engine: Custom AI engine for black. None = default from difficulty.
            white_engine: Custom AI engine for white. None = default from difficulty.
            position: 32-char position string. None = standard opening.
            auto_ai: If True, both sides use AI by default.
        """
        self._board = Board(empty=position is not None)
        if position is not None:
            self._board.load_from_position_string(position)
        else:
            self._board = Board()

        self._turn: Color = Color.WHITE
        self._ply: int = 0
        self._is_over: bool = False
        self._result: GameResult | None = None
        self._moves: list[MoveRecord] = []
        self._position_history: list[str] = [self._board.to_position_string()]
        self._position_counts: dict[str, int] = {self._board.to_position_string(): 1}
        # Quiet half-moves counter (reset on any capture). Used by
        # play_full_game to detect sterile endgames (draughts' analogue
        # of the chess 50-move rule).
        self._quiet_plies: int = 0
        # Wall-clock of the most recent AI move. Useful for heartbeat logs.
        self._last_move_time_s: float = 0.0

        # AI engines
        self._engines: dict[Color, AIEngine | None] = {
            Color.BLACK: black_engine or (AIEngine(difficulty=difficulty, color=Color.BLACK, search_depth=depth) if auto_ai else None),
            Color.WHITE: white_engine or (AIEngine(difficulty=difficulty, color=Color.WHITE, search_depth=depth) if auto_ai else None),
        }

    # --- Properties ---

    @property
    def board(self) -> Board:
        return self._board

    @property
    def turn(self) -> Color:
        return self._turn

    @property
    def ply_count(self) -> int:
        return self._ply

    @property
    def is_over(self) -> bool:
        return self._is_over

    @property
    def result(self) -> GameResult | None:
        return self._result

    @property
    def moves(self) -> list[MoveRecord]:
        return list(self._moves)

    @property
    def position_string(self) -> str:
        return self._board.to_position_string()

    # --- Core game actions ---

    def make_ai_move(self, move_timeout: float = 0.0) -> MoveRecord | None:
        """Let AI make a move for the current side.

        Args:
            move_timeout: Max wall-clock seconds the AI may spend on this
                move. 0 = no limit. Enforced via cooperative cancellation
                inside alpha-beta — the search gracefully returns the best
                move from the last fully completed iterative-deepening
                depth (never a partial-depth result, never None if a legal
                move exists). Unlike a thread-based timeout, no search
                ever keeps running after this call returns.

        Sets self._last_move_time_s to the wall-clock elapsed for the
        search. Returns MoveRecord, or None if the game is over, the side
        has no engine, or the side has no legal moves (in which case the
        game ends with reason "no_moves").
        """
        if self._is_over:
            return None

        engine = self._engines.get(self._turn)
        if engine is None:
            engine = AIEngine(difficulty=2, color=self._turn)

        eval_before = evaluate_position(self._board.grid, self._turn)

        deadline = time.perf_counter() + move_timeout if move_timeout > 0 else None
        t0 = time.perf_counter()
        move = engine.find_move(self._board.copy(), deadline=deadline)
        self._last_move_time_s = time.perf_counter() - t0

        if move is None:
            self._end_game(self._turn.opponent, "no_moves")
            return None

        return self._execute_ai_move(move, eval_before)

    def make_move(self, from_pos: str | tuple[int, int], to_pos: str | tuple[int, int]) -> MoveRecord | None:
        """Make a manual move.

        Args:
            from_pos: Starting position as notation ("c3") or (x, y) tuple.
            to_pos: Target position as notation ("d4") or (x, y) tuple.

        Returns MoveRecord if valid, None if invalid/illegal.
        """
        if self._is_over:
            return None

        x1, y1 = self._parse_pos(from_pos)
        x2, y2 = self._parse_pos(to_pos)

        # Check piece belongs to current side
        piece = self._board.piece_at(x1, y1)
        if piece == Board.EMPTY:
            return None
        if self._turn == Color.WHITE and not Board.is_white(piece):
            return None
        if self._turn == Color.BLACK and not Board.is_black(piece):
            return None

        eval_before = evaluate_position(self._board.grid, self._turn)

        # Check captures first (mandatory)
        if self._board.has_any_capture(self._turn):
            captures = self._board.get_captures(x1, y1)
            for path in captures:
                if len(path) >= 2 and path[-1] == (x2, y2):
                    self._board.execute_capture_path(path)
                    notation = ":".join(Board.pos_to_notation(x, y) for x, y in path)
                    eval_after = evaluate_position(self._board.grid, self._turn)
                    return self._record_move("capture", path, notation, eval_before, eval_after)
            return None  # invalid capture

        # Normal move
        valid = self._board.get_valid_moves(x1, y1)
        if (x2, y2) not in valid:
            return None

        self._board.execute_move(x1, y1, x2, y2)
        path = [(x1, y1), (x2, y2)]
        notation = f"{Board.pos_to_notation(x1, y1)}-{Board.pos_to_notation(x2, y2)}"
        eval_after = evaluate_position(self._board.grid, self._turn)
        return self._record_move("move", path, notation, eval_before, eval_after)

    def make_capture(self, path: list[str | tuple[int, int]]) -> MoveRecord | None:
        """Make a multi-step capture with explicit path.

        Args:
            path: List of positions (notation or tuples) the piece visits.

        Returns MoveRecord if valid, None if invalid.
        """
        if self._is_over or len(path) < 2:
            return None

        parsed = [self._parse_pos(p) for p in path]
        x1, y1 = parsed[0]

        piece = self._board.piece_at(x1, y1)
        if piece == Board.EMPTY:
            return None

        captures = self._board.get_captures(x1, y1)
        if parsed in captures:
            eval_before = evaluate_position(self._board.grid, self._turn)
            self._board.execute_capture_path(parsed)
            notation = ":".join(Board.pos_to_notation(x, y) for x, y in parsed)
            eval_after = evaluate_position(self._board.grid, self._turn)
            return self._record_move("capture", parsed, notation, eval_before, eval_after)
        return None

    def step(self) -> MoveRecord | None:
        """Execute one AI move for current side. Alias for make_ai_move."""
        return self.make_ai_move()

    def play_full_game(
        self,
        max_ply: int = 200,
        move_timeout: float = 0.0,
        game_timeout: float = 0.0,
        quiet_move_limit: int = 0,
        quiet_move_limit_endgame: int = 0,
        endgame_piece_threshold: int = 6,
        heartbeat: Callable[[HeadlessGame, MoveRecord], None] | None = None,
    ) -> GameResult:
        """Play a complete AI vs AI game with hard termination guarantees.

        Every limit below, when non-zero, is an independent hard cap. The
        first one hit wins. This is intended for dev-mode automation where
        the caller must keep control and never hang.

        Args:
            max_ply: Maximum half-moves before declaring a draw (reason
                "draw_max_ply"). 0 = no cap (not recommended for dev).
            move_timeout: Max seconds per AI move. Enforced cooperatively
                inside the search; the engine returns the best move from
                the last fully completed depth instead of running over.
                0 = no per-move cap.
            game_timeout: Max wall-clock seconds for the whole game.
                Checked before each move. On hit, ends with reason
                "timeout_game". 0 = no cap.
            quiet_move_limit: After this many consecutive half-moves
                without a capture in the middlegame (more than
                endgame_piece_threshold pieces on the board), declare a
                draw with reason "draw_quiet". 0 = disabled. Reasonable
                default: 40.
            quiet_move_limit_endgame: Same as above but applied whenever
                total piece count <= endgame_piece_threshold. Kept shorter
                so king-vs-king shuffling terminates fast. 0 = disabled.
                Reasonable default: 15.
            endgame_piece_threshold: Piece count at or below which the
                endgame quiet limit kicks in. Default 6.
            heartbeat: Optional callback invoked after every successful
                move with (self, record). Used by the dev CLI to append
                per-move lines to a log file so an outside watcher can
                tell a stuck process from a slow one.

        Returns GameResult. Possible reasons:
            - "no_pieces": one side lost all pieces
            - "no_moves": one side has no legal moves
            - "draw_repetition": 3-fold position repetition
            - "draw_max_ply": reached max_ply limit
            - "draw_quiet": quiet-move (no-capture) limit reached
            - "timeout_game": game_timeout elapsed
        """
        t_game_start = time.perf_counter()
        while not self._is_over:
            if max_ply > 0 and self._ply >= max_ply:
                break
            if game_timeout > 0 and (time.perf_counter() - t_game_start) >= game_timeout:
                self._end_game(None, "timeout_game")
                break

            record = self.make_ai_move(move_timeout=move_timeout)
            if record is None:
                # make_ai_move already called _end_game for no-moves cases;
                # if it did not, force-end defensively so we cannot spin.
                if not self._is_over:
                    self._end_game(self._turn.opponent, "no_moves")
                break

            if heartbeat is not None:
                try:
                    heartbeat(self, record)
                except Exception:
                    # A broken heartbeat must never take the game down.
                    pass

            # Sterile-endgame detection — the draughts analogue of the
            # chess 50-move rule. Two different thresholds: a loose one
            # for the middlegame, a tight one for the endgame where kings
            # cycling through distinct (non-repeating) positions would
            # otherwise never trigger the 3-fold rule.
            piece_count = self._board.count_pieces(Color.BLACK) + self._board.count_pieces(Color.WHITE)
            is_endgame = piece_count <= endgame_piece_threshold
            limit = quiet_move_limit_endgame if is_endgame else quiet_move_limit
            if limit > 0 and self._quiet_plies >= limit:
                self._end_game(None, "draw_quiet")
                break

        if not self._is_over:
            self._end_game(None, "draw_max_ply")

        return self._result  # type: ignore[return-value]

    # --- Analysis ---

    def evaluate(self) -> float:
        """Evaluate current position from current side's perspective."""
        return evaluate_position(self._board.grid, self._turn)

    def get_ai_analysis(self, depth: int = 6) -> Analysis:
        """Analyze current position.

        Mirrors AIEngine.find_move's adaptive-depth behaviour so that the
        analysis reflects how the AI will actually play: in sparse
        endgames it applies a small depth bonus, and in crowded openings
        it caps the depth. Previously get_ai_analysis skipped this,
        which meant `dev.py analyze --depth 8` could report a different
        move than the AI would pick at runtime in the same position.

        The reported `score` is the minimax score from the search, not
        a static eval of the pre-move position. `static_score` still
        exposes the raw eval for comparison.
        """
        moves = _generate_all_moves(self._board, self._turn)
        effective_depth = adaptive_depth(depth, self._board)
        best = _search_best_move(self._board, self._turn, effective_depth)
        static = evaluate_position(self._board.grid, self._turn)
        # _last_search_score is populated as a side effect of
        # _search_best_move. If search returned None (no legal moves),
        # fall back to the static eval.
        search_score = _ai._last_search_score if best is not None else static
        return Analysis(
            best_move=best,
            score=search_score,
            static_score=static,
            depth=effective_depth,
            legal_move_count=len(moves),
        )

    def get_legal_moves(self) -> list[tuple[str, list[tuple[int, int]]]]:
        """Get all legal moves for current side.

        Returns list of (kind, path) tuples.
        """
        return _generate_all_moves(self._board, self._turn)

    # --- Serialization ---

    def to_dict(self) -> dict:
        """Serialize game state to dict."""
        return {
            "position": self._board.to_position_string(),
            "turn": str(self._turn),
            "ply": self._ply,
            "is_over": self._is_over,
            "moves": [
                {
                    "ply": m.ply,
                    "color": str(m.color),
                    "notation": m.notation,
                    "kind": m.kind,
                    "path": m.path,
                    "eval_before": m.eval_before,
                    "eval_after": m.eval_after,
                }
                for m in self._moves
            ],
            "position_history": self._position_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HeadlessGame:
        """Deserialize game state from dict."""
        game = cls(position=data["position"], auto_ai=True)
        game._turn = Color(data["turn"])
        game._ply = data["ply"]
        game._is_over = data["is_over"]
        game._position_history = data.get("position_history", [])
        game._moves = [
            MoveRecord(
                ply=m["ply"],
                color=Color(m["color"]),
                notation=m["notation"],
                kind=m["kind"],
                path=[tuple(p) for p in m["path"]],
                eval_before=m["eval_before"],
                eval_after=m["eval_after"],
            )
            for m in data.get("moves", [])
        ]
        return game

    def format_move_list(self) -> str:
        """Format move history in standard notation.

        Returns string like:
            1. c3-d4  f6-e5
            2. b2-c3  g7-f6
        """
        lines = []
        move_num = 1
        i = 0
        while i < len(self._moves):
            white_move = self._moves[i].notation if i < len(self._moves) else ""
            black_move = self._moves[i + 1].notation if i + 1 < len(self._moves) else ""
            lines.append(f"{move_num}. {white_move}  {black_move}")
            move_num += 1
            i += 2
        return "\n".join(lines)

    # --- Internal ---

    def _parse_pos(self, pos: str | tuple[int, int]) -> tuple[int, int]:
        """Parse position from notation string or (x, y) tuple."""
        if isinstance(pos, str):
            return Board.notation_to_pos(pos)
        return pos

    def _execute_ai_move(self, move: AIMove, eval_before: float) -> MoveRecord:
        """Execute an AIMove on the board and record it."""
        if move.kind == "capture":
            self._board.execute_capture_path(move.path)
            notation = ":".join(Board.pos_to_notation(x, y) for x, y in move.path)
        else:
            x1, y1 = move.path[0]
            x2, y2 = move.path[1]
            self._board.execute_move(x1, y1, x2, y2)
            notation = f"{Board.pos_to_notation(x1, y1)}-{Board.pos_to_notation(x2, y2)}"

        eval_after = evaluate_position(self._board.grid, self._turn)
        return self._record_move(move.kind, move.path, notation, eval_before, eval_after)

    def _record_move(
        self,
        kind: str,
        path: list[tuple[int, int]],
        notation: str,
        eval_before: float,
        eval_after: float,
    ) -> MoveRecord:
        """Record move, update state, check game over."""
        record = MoveRecord(
            ply=self._ply,
            color=self._turn,
            notation=notation,
            kind=kind,
            path=list(path),
            eval_before=eval_before,
            eval_after=eval_after,
        )
        self._moves.append(record)
        self._ply += 1

        # Quiet-move counter: reset to zero on any capture, otherwise
        # increment. A promotion-only move (no capture) still counts as
        # quiet; that is fine because promotions change material count
        # and will unblock the 3-fold/repetition check via distinct
        # positions. The counter exists to catch sterile king-dances.
        if kind == "capture":
            self._quiet_plies = 0
        else:
            self._quiet_plies += 1

        pos = self._board.to_position_string()
        self._position_history.append(pos)
        self._position_counts[pos] = self._position_counts.get(pos, 0) + 1

        # Check for repetition draw (3-fold)
        if self._position_counts[pos] >= 3:
            self._end_game(None, "draw_repetition")
            return record

        # Check for game over
        opp = self._turn.opponent
        opp_pieces = self._board.count_pieces(opp)
        if opp_pieces == 0:
            self._end_game(self._turn, "no_pieces")
            return record

        cur_pieces = self._board.count_pieces(self._turn)
        if cur_pieces == 0:
            self._end_game(opp, "no_pieces")
            return record

        if not self._board.has_any_move(opp):
            self._end_game(self._turn, "no_moves")
            return record

        # Switch turn
        self._turn = opp
        return record

    def _end_game(self, winner: Color | None, reason: str) -> None:
        """End the game with given result."""
        self._is_over = True
        self._result = GameResult(
            winner=winner,
            reason=reason,
            ply_count=self._ply,
            moves=list(self._moves),
            final_position=self._board.to_position_string(),
        )
