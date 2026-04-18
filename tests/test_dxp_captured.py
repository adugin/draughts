"""DXP server must emit enemy-piece squares (not landing squares) in
the MOVE frame's ``captured`` field.

Prior implementation wrote the intermediate landing squares from our
own AIMove.path. For short pawn hops those are the same as enemy
squares — round-trip with ourselves happened to work. But for flying
kings whose landing and enemy squares differ (e.g. king slides
a1→f6 over an enemy at c3), we sent the landing squares and any
third-party DXP peer would have rejected the move as malformed.

Disambiguation of multiple paths sharing from/to (_dxp_to_move_path)
had the same bug on the decode side.
"""

from __future__ import annotations

from draughts.config import BLACK, BLACK_KING, Color, WHITE, WHITE_KING
from draughts.engine.dxp import Move
from draughts.engine.dxp_server import (
    _dxp_to_move_path,
    _enemy_square_numbers,
    _move_to_dxp,
)
from draughts.game.ai.search import AIMove
from draughts.game.board import Board
from draughts.game.pdn import xy_to_square


def _place(b: Board, notation: str, piece: int) -> None:
    x, y = Board.notation_to_pos(notation)
    b.place_piece(x, y, piece)


def test_enemy_squares_for_short_pawn_capture():
    # White pawn c3 jumps black pawn on d4 landing on e5: enemy is d4.
    b = Board(empty=True)
    _place(b, "c3", int(WHITE))
    _place(b, "d4", int(BLACK))
    path = [Board.notation_to_pos("c3"), Board.notation_to_pos("e5")]
    enemy = _enemy_square_numbers(path, b)
    assert enemy == [xy_to_square(*Board.notation_to_pos("d4"))]


def test_enemy_squares_for_flying_king_capture_differs_from_landing():
    # White king at a1 slides diagonally, jumping black pawn at c3,
    # landing at e5. Landing point is e5 (x=4,y=3), enemy is c3.
    b = Board(empty=True)
    _place(b, "a1", int(WHITE_KING))
    _place(b, "c3", int(BLACK))
    path = [Board.notation_to_pos("a1"), Board.notation_to_pos("e5")]
    enemy = _enemy_square_numbers(path, b)
    assert enemy == [xy_to_square(*Board.notation_to_pos("c3"))]
    # Sanity: enemy square is NOT the destination.
    assert enemy != [xy_to_square(*Board.notation_to_pos("e5"))]


def test_move_to_dxp_emits_enemy_squares_not_landing_squares():
    b = Board(empty=True)
    _place(b, "a1", int(WHITE_KING))
    _place(b, "c3", int(BLACK))
    move = AIMove(kind="capture", path=[
        Board.notation_to_pos("a1"),
        Board.notation_to_pos("e5"),
    ])
    dxp_move = _move_to_dxp(move, time_used=0.0, before=b)
    expected_enemy_sq = xy_to_square(*Board.notation_to_pos("c3"))
    assert dxp_move.captured == [expected_enemy_sq]


def test_move_to_dxp_multi_jump_lists_each_enemy_square():
    # White king a1 → e5 (jumps black at c3) → g7 (jumps black at f6).
    b = Board(empty=True)
    _place(b, "a1", int(WHITE_KING))
    _place(b, "c3", int(BLACK))
    _place(b, "f6", int(BLACK))
    path = [
        Board.notation_to_pos("a1"),
        Board.notation_to_pos("e5"),
        Board.notation_to_pos("g7"),
    ]
    move = AIMove(kind="capture", path=path)
    dxp_move = _move_to_dxp(move, time_used=0.0, before=b)
    expected = [
        xy_to_square(*Board.notation_to_pos("c3")),
        xy_to_square(*Board.notation_to_pos("f6")),
    ]
    assert dxp_move.captured == expected


def test_move_to_dxp_simple_move_has_empty_captured():
    b = Board()
    move = AIMove(kind="move", path=[
        Board.notation_to_pos("c3"),
        Board.notation_to_pos("b4"),
    ])
    dxp_move = _move_to_dxp(move, time_used=0.0, before=b)
    assert dxp_move.captured == []


def test_dxp_to_move_path_accepts_enemy_squares_for_disambiguation():
    """Peer sends enemy-piece squares per spec — we must accept that
    form during ambiguous-path disambiguation, not just the old
    landing-squares encoding."""
    # Two black pawns sit symmetrically around a white king's diagonals
    # so the king has multiple legal capture paths ending at the same
    # target. We build a minimal case with a single path where
    # landing == enemy (short hop) to keep the test deterministic.
    b = Board(empty=True)
    _place(b, "a1", int(WHITE_KING))
    _place(b, "c3", int(BLACK))
    # Peer move frame with captured=[c3 square number], per spec.
    c3_sq = xy_to_square(*Board.notation_to_pos("c3"))
    a1_sq = xy_to_square(*Board.notation_to_pos("a1"))
    e5_sq = xy_to_square(*Board.notation_to_pos("e5"))
    peer = Move(time_centis=0, from_sq=a1_sq, to_sq=e5_sq, captured=[c3_sq])
    # Normal (non-ambiguous) probe — should succeed because endpoint
    # matching finds exactly one legal capture.
    path = _dxp_to_move_path(peer, b, Color.WHITE)
    assert path is not None
    assert path[0] == Board.notation_to_pos("a1")
    assert path[-1] == Board.notation_to_pos("e5")


def test_dxp_round_trip_flying_king_capture():
    """A round trip through encode/decode and back to a legal path must
    recover the same path when enemy squares are used on both sides."""
    b = Board(empty=True)
    _place(b, "a1", int(WHITE_KING))
    _place(b, "c3", int(BLACK))
    move = AIMove(kind="capture", path=[
        Board.notation_to_pos("a1"),
        Board.notation_to_pos("e5"),
    ])
    dxp_move = _move_to_dxp(move, time_used=0.0, before=b)
    # Feed back through the decoder on an identical pre-move board.
    recovered = _dxp_to_move_path(dxp_move, b, Color.WHITE)
    assert recovered is not None
    assert recovered[0] == Board.notation_to_pos("a1")
    assert recovered[-1] == Board.notation_to_pos("e5")
