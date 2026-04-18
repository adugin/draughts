"""Regression tests for the bitbase tie-break bug (king_blunder_bug.pdn).

Bug summary:
    When multiple legal moves all map to a WIN in the endgame bitbase,
    _bitbase_best_move used to tie-break via _order_moves (captures
    first, then center control) — which is oblivious to material.
    In positions with a mandatory capture reply, the engine would
    sometimes pick a move that immediately lost a king to the opponent
    but still reached a (bitbase-winning) position, looking like a blunder.

Fix: tie-break WIN moves by static eval so the engine prefers the one
that preserves material.

User report position (king_blunder_bug.pdn): 2 black kings (a1, h6)
vs 1 white pawn (c5), black to move. Old engine picked a1-d4, which
lost the king to c5:e3. New engine picks h6-c1 (keeps both kings).
"""

from __future__ import annotations

from draughts.config import BLACK_KING, WHITE, Color
from draughts.game.ai import AIEngine
from draughts.game.board import Board


def _two_kings_vs_pawn_black_to_move() -> Board:
    b = Board(empty=True)
    b.grid[7, 0] = BLACK_KING  # a1
    b.grid[2, 7] = BLACK_KING  # h6
    b.grid[3, 2] = WHITE       # c5
    return b


def _algebraic(path) -> tuple[str, str]:
    return (Board.pos_to_notation(*path[0]), Board.pos_to_notation(*path[-1]))


def test_ai_does_not_walk_king_into_pawn_capture():
    """2K (a1, h6) vs 1P (c5), black to move: AI must NOT play a1-d4.

    a1-d4 is disastrous for the human even though the bitbase labels the
    resulting win as equivalent to other WIN moves. The engine must
    prefer a move that preserves both kings.
    """
    b = _two_kings_vs_pawn_black_to_move()
    engine = AIEngine(difficulty=6, color=Color.BLACK, use_book=True, use_bitbase=True)
    move = engine.find_move(b)
    assert move is not None

    src, dst = _algebraic(move.path)
    # Explicitly forbid the three moves that step into the pawn's
    # capture radius. c5 captures a neighbour by jumping to the square
    # two diagonals away. From c5, pawn-capture destinations include
    # e3 (over d4), a3 (over b4), a7 (over b6), e7 (over d6).
    forbidden_destinations = {"d4", "b4", "b6", "d6"}
    assert dst not in forbidden_destinations, (
        f"AI chose {src}-{dst}, placing a king under c5-pawn capture. "
        "Tie-break must prefer material-preserving moves over trades."
    )


def test_winning_tiebreak_prefers_higher_eval():
    """Among multiple bitbase-WIN moves, the one with better static eval wins."""
    from draughts.game.ai.eval import _evaluate_fast
    from draughts.game.ai.moves import _apply_move, _generate_all_moves

    b = _two_kings_vs_pawn_black_to_move()
    engine = AIEngine(difficulty=6, color=Color.BLACK, use_book=True, use_bitbase=True)
    move = engine.find_move(b)
    assert move is not None

    # Ensure the chosen move's eval (from black's perspective) is at
    # least as high as the rejected a1-d4 eval.
    chosen_child = _apply_move(b, move.kind, move.path)
    chosen_eval = _evaluate_fast(chosen_child.grid, Color.BLACK)

    d4_move = None
    for kind, path in _generate_all_moves(b, Color.BLACK):
        if Board.pos_to_notation(*path[0]) == "a1" and Board.pos_to_notation(*path[-1]) == "d4":
            d4_move = (kind, path)
            break
    assert d4_move is not None
    d4_child = _apply_move(b, d4_move[0], d4_move[1])
    d4_eval = _evaluate_fast(d4_child.grid, Color.BLACK)

    assert chosen_eval >= d4_eval, (
        f"Chosen move {move.path} eval={chosen_eval} must be >= the "
        f"discarded a1-d4 eval={d4_eval}."
    )
