"""Position analysis — isolated from HeadlessGame game-flow concerns.

This module owns the Analysis dataclass and the get_ai_analysis() free
function.  It has no PyQt6 dependency and can be imported in any headless
context (tests, CLI tools, parallel tournament workers).

Separation rationale (MODULE_AUDIT.md Step 5):
    Analysis of a position (evaluate score, report depth, best move) has a
    different change velocity from game-flow concerns (apply move, detect draw,
    record history).  Isolating it here means AI analysis bugs can be fixed
    without touching HeadlessGame's game-end logic.

Thread safety:
    Each call to get_ai_analysis() creates a fresh SearchContext, so
    concurrent calls on different HeadlessGame instances are safe.
    No module-level mutable state is read or written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from draughts.game.ai import (
    AIMove,
    _generate_all_moves,
    _search_best_move,
    adaptive_depth,
    evaluate_position,
)
from draughts.game.ai.state import SearchContext

if TYPE_CHECKING:
    # Avoid a circular import at runtime: analysis → headless would be cyclic
    # because headless already re-exports Analysis from this module.
    from draughts.game.headless import HeadlessGame


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


def get_ai_analysis(game: HeadlessGame, depth: int = 6) -> Analysis:
    """Analyze the current position of a HeadlessGame.

    Mirrors AIEngine.find_move's adaptive-depth behaviour so that the
    analysis reflects how the AI will actually play: in sparse endgames it
    applies a small depth bonus, and in crowded openings it caps the depth.

    The reported ``score`` is the minimax score from the search, not a
    static eval of the pre-move position.  ``static_score`` still exposes
    the raw eval for comparison.

    Thread safety: creates a fresh SearchContext per call, so concurrent
    calls on different game instances are safe.

    Args:
        game: A HeadlessGame instance in any position/state.
        depth: Requested search depth (adaptive_depth may adjust it).

    Returns:
        Analysis dataclass with best_move, score, static_score, depth,
        and legal_move_count.
    """
    board = game.board
    color = game.turn

    moves = _generate_all_moves(board, color)
    effective_depth = adaptive_depth(depth, board)
    static = evaluate_position(board.grid, color)

    # Use a fresh, isolated SearchContext so parallel calls cannot interfere.
    ctx = SearchContext()
    best = _search_best_move(board, color, effective_depth, ctx=ctx)

    # ctx.last_score is set by _search_best_move to the minimax value of the
    # returned move.  Fall back to static eval when there are no legal moves.
    search_score = ctx.last_score if best is not None else static

    return Analysis(
        best_move=best,
        score=search_score,
        static_score=static,
        depth=effective_depth,
        legal_move_count=len(moves),
    )


def compute_pv(
    game: "HeadlessGame",
    depth: int = 6,
    pv_length: int = 5,
) -> list[AIMove]:
    """Compute a principal variation — the AI's best-line continuation.

    Iteratively: find best move, apply it, find best response, apply, ...
    Stops early when the position has no legal moves (game-over) or
    ``pv_length`` is reached.

    Each internal search uses a fresh ``SearchContext`` so this call is
    safe to run concurrently with ``get_ai_analysis`` on other games.

    Args:
        game: HeadlessGame whose current position is the PV start.
            The game is NOT mutated — all work is on board copies.
        depth: Requested depth for every PV ply.
        pv_length: Maximum number of moves in the returned PV.

    Returns:
        List of AIMove objects, length ≤ pv_length. Empty list if the
        start position has no legal moves.
    """
    from draughts.game.board import Board
    from draughts.config import Color

    pv: list[AIMove] = []
    if pv_length <= 0:
        return pv
    depth = max(1, int(depth))
    pv_length = max(1, int(pv_length))
    # Work on a fresh Board copy so ``game.board`` is untouched.
    board = Board()
    board.load_from_position_string(game.board.to_position_string())
    color: Color = game.turn

    for _ in range(pv_length):
        moves = _generate_all_moves(board, color)
        if not moves:
            break
        eff_depth = adaptive_depth(depth, board)
        ctx = SearchContext()
        best = _search_best_move(board, color, eff_depth, ctx=ctx)
        if best is None:
            break
        pv.append(best)

        # Apply the move to the local board and swap side-to-move.
        if best.kind == "capture":
            board.execute_capture_path(best.path)
        else:
            (x1, y1), (x2, y2) = best.path[0], best.path[1]
            board.execute_move(x1, y1, x2, y2)
        color = color.opponent

    return pv
