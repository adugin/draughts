"""FEN (Forsyth-Edwards Notation) for Russian draughts 8x8.

Russian-draughts FEN format (PDN 3.0 standard):
    W:WK1,K5,15,19:BK28,K32,9,22

Where:
  - First token: side to move (W or B)
  - Colon-separated lists for each side, white first
  - Inside each list: comma-separated square numbers (1-32)
  - Prefix 'K' before a square number marks a king

Square numbering matches PDN 1-32 scheme for Russian 8x8.

Reference: https://wiegerw.github.io/pdn/pdntags.html
"""

from __future__ import annotations

from draughts.config import BLACK, BLACK_KING, WHITE, WHITE_KING, Color
from draughts.game.board import Board
from draughts.game.pdn import square_to_xy, xy_to_square

# ---------------------------------------------------------------------------
# Start-position FEN for Russian draughts 8x8
# ---------------------------------------------------------------------------

START_FEN = "W:W21,22,23,24,25,26,27,28,29,30,31,32:B1,2,3,4,5,6,7,8,9,10,11,12"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_fen(fen: str) -> tuple[Board, Color]:
    """Parse a Russian-draughts FEN string into (Board, Color).

    Args:
        fen: FEN string, e.g. 'W:WK1,K5,15,19:BK28,K32,9,22'
              or the start-position FEN.

    Returns:
        (board, color) where board is a Board instance and color is the
        side to move (Color.WHITE or Color.BLACK).

    Raises:
        ValueError: if the FEN is malformed.
    """
    from draughts.game.board import Board

    board = Board(empty=True)

    fen = fen.strip()
    if not fen:
        raise ValueError("Empty FEN string")

    parts = fen.split(":")

    # Side to move
    side_token = parts[0].strip().upper()
    if side_token == "W":  # noqa: S105
        color = Color.WHITE
    elif side_token == "B":  # noqa: S105
        color = Color.BLACK
    else:
        raise ValueError(f"Invalid side-to-move in FEN: {side_token!r}")

    # Parse piece lists — can be W... and B... in any order
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        part_upper = part.upper()
        if part_upper.startswith("W"):
            side_char = "W"
            piece_list_str = part[1:]
        elif part_upper.startswith("B"):
            side_char = "B"
            piece_list_str = part[1:]
        else:
            raise ValueError(f"Invalid piece list in FEN: {part!r}")

        if not piece_list_str:
            continue

        for token in piece_list_str.split(","):
            token = token.strip()
            if not token:
                continue
            is_king = token.upper().startswith("K")
            sq_str = token[1:] if is_king else token
            try:
                sq = int(sq_str)
            except ValueError as exc:
                raise ValueError(f"Invalid square number in FEN token {token!r}") from exc

            x, y = square_to_xy(sq)
            piece = int((WHITE_KING if is_king else WHITE) if side_char == "W" else (BLACK_KING if is_king else BLACK))
            board.place_piece(x, y, piece)

    return board, color


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------


def board_to_fen(board: Board, color: Color) -> str:
    """Serialize a board position to Russian-draughts FEN string.

    Args:
        board: Board instance.
        color: Side to move.

    Returns:
        FEN string, e.g. 'W:W21,22,23,24:BK1,5,9'
    """
    side = "W" if color == Color.WHITE else "B"

    white_men: list[int] = []
    white_kings: list[int] = []
    black_men: list[int] = []
    black_kings: list[int] = []

    for y in range(8):
        for x in range(8):
            if x % 2 == y % 2:
                continue  # light square, skip
            piece = board.piece_at(x, y)
            if piece == 0:
                continue
            sq = xy_to_square(x, y)
            if piece == WHITE:
                white_men.append(sq)
            elif piece == WHITE_KING:
                white_kings.append(sq)
            elif piece == BLACK:
                black_men.append(sq)
            elif piece == BLACK_KING:
                black_kings.append(sq)

    # Sort for deterministic output
    white_men.sort()
    white_kings.sort()
    black_men.sort()
    black_kings.sort()

    white_tokens = [f"K{sq}" for sq in white_kings] + [str(sq) for sq in white_men]
    black_tokens = [f"K{sq}" for sq in black_kings] + [str(sq) for sq in black_men]

    white_part = "W" + ",".join(white_tokens) if white_tokens else "W"
    black_part = "B" + ",".join(black_tokens) if black_tokens else "B"

    return f"{side}:{white_part}:{black_part}"
