"""Headless game engine — programmatic control without GUI.

Provides HeadlessGame for running complete games, analyzing positions,
and testing AI behavior without PyQt6 event loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from draughts.config import Color
from draughts.game.ai import (
    AIEngine,
    AIMove,
    _generate_all_moves,
    _search_best_move,
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
    reason: str  # "no_pieces", "no_moves", "draw_repetition", "draw_max_ply"
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
    """AI analysis of a position."""

    best_move: AIMove | None
    score: float  # from perspective of side to move
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

    def make_ai_move(self) -> MoveRecord | None:
        """Let AI make a move for the current side.

        Returns MoveRecord or None if game is over / no engine.
        """
        if self._is_over:
            return None

        engine = self._engines.get(self._turn)
        if engine is None:
            engine = AIEngine(difficulty=2, color=self._turn)

        eval_before = evaluate_position(self._board.grid, self._turn)
        move = engine.find_move(self._board.copy())

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

    def play_full_game(self, max_ply: int = 200) -> GameResult:
        """Play complete AI vs AI game.

        Returns GameResult when game ends.
        """
        while not self._is_over and self._ply < max_ply:
            result = self.make_ai_move()
            if result is None and not self._is_over:
                self._end_game(self._turn.opponent, "no_moves")
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

        Returns Analysis with best move, score, and legal move count.
        """
        moves = _generate_all_moves(self._board, self._turn)
        best = _search_best_move(self._board, self._turn, depth)
        score = evaluate_position(self._board.grid, self._turn)
        return Analysis(
            best_move=best,
            score=score,
            depth=depth,
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
