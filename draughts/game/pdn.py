"""PDN (Portable Draughts Notation) parser and writer.

Supports reading/writing game records in standard PDN 3.0 format
used by draughts databases worldwide.

PDN format example:
    [Event "Tournament"]
    [White "Player A"]
    [Black "Player B"]
    [Result "1-0"]
    [GameType "25,W,8,8,A1,0"]
    1. 23-19 9-14 2. 27-23 5-9

Note: PDN uses numeric square numbering (1-32 for 8x8 board).
We convert to/from our (x,y) coordinate system as needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from draughts.game.gametree import NAG_MAP, NAG_REVERSE, GameNode, GameTree

if TYPE_CHECKING:
    from draughts.game.board import Board


@dataclass
class PDNGame:
    """A single game record in PDN format.

    ``moves`` is the main-line move list (backward compat with code written
    before M5). ``tree`` is the full variation tree (populated by the
    RAV-aware parser; when None, callers can build one via
    GameTree.from_moves(game.moves)).
    """

    headers: dict[str, str] = field(default_factory=dict)
    moves: list[str] = field(default_factory=list)
    tree: GameTree | None = field(default=None, repr=False)

    @property
    def event(self) -> str:
        return self.headers.get("Event", "?")

    @property
    def white(self) -> str:
        return self.headers.get("White", "?")

    @property
    def black(self) -> str:
        return self.headers.get("Black", "?")

    @property
    def result(self) -> str:
        return self.headers.get("Result", "*")


# ---------------------------------------------------------------------------
# Square numbering for 8x8 Russian draughts board
# Standard numbering: 1-32, left-to-right, top-to-bottom on dark squares
# Our coordinates: (x, y) where x=column (0-7), y=row (0-7)
# ---------------------------------------------------------------------------

# Build conversion tables
_SQUARE_TO_XY: dict[int, tuple[int, int]] = {}
_XY_TO_SQUARE: dict[tuple[int, int], int] = {}

_sq = 1
for _y in range(8):
    for _x in range(8):
        if _x % 2 != _y % 2:  # dark square
            _SQUARE_TO_XY[_sq] = (_x, _y)
            _XY_TO_SQUARE[(_x, _y)] = _sq
            _sq += 1


def square_to_xy(sq: int) -> tuple[int, int]:
    """Convert PDN square number (1-32) to (x, y) coordinates."""
    if sq not in _SQUARE_TO_XY:
        raise ValueError(f"Invalid square number: {sq} (must be 1-32)")
    return _SQUARE_TO_XY[sq]


def xy_to_square(x: int, y: int) -> int:
    """Convert (x, y) coordinates to PDN square number (1-32)."""
    key = (x, y)
    if key not in _XY_TO_SQUARE:
        raise ValueError(f"({x}, {y}) is not a dark square")
    return _XY_TO_SQUARE[key]


def notation_to_pdn_move(notation: str) -> str:
    """Convert our notation (e.g. 'c3-d4' or 'f6:d4:b2') to PDN numeric format.

    'c3-d4' → '22-17' (example numbers)
    'f6:d4:b2' → '11x18x25' (example numbers)
    """
    from draughts.game.board import Board

    sep = ":" if ":" in notation else "-"
    pdn_sep = "x" if sep == ":" else "-"

    parts = notation.split(sep)
    pdn_parts = []
    for part in parts:
        x, y = Board.notation_to_pos(part)
        pdn_parts.append(str(xy_to_square(x, y)))
    return pdn_sep.join(pdn_parts)


def pdn_move_to_notation(pdn_move: str) -> str:
    """Convert PDN numeric move (e.g. '22-17' or '11x18x25') to our notation.

    '22-17' → 'c3-d4' (example)
    '11x18x25' → 'f6:d4:b2' (example)
    """
    from draughts.game.board import Board

    is_capture = "x" in pdn_move
    sep = "x" if is_capture else "-"
    our_sep = ":" if is_capture else "-"

    parts = pdn_move.split(sep)
    notation_parts = []
    for part in parts:
        sq = int(part.strip())
        x, y = square_to_xy(sq)
        notation_parts.append(Board.pos_to_notation(x, y))
    return our_sep.join(notation_parts)


# ---------------------------------------------------------------------------
# Canonical tag order for PDN 3.0
# ---------------------------------------------------------------------------

_CANONICAL_TAGS = ["Event", "Site", "Date", "Round", "White", "Black", "Result", "GameType"]
# SetUp / FEN come after these if present
_SETUP_TAGS = ["SetUp", "FEN"]

RUSSIAN_DRAUGHTS_GAMETYPE = "25,W,8,8,A1,0"
_RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def pdngame_to_string(game: PDNGame) -> str:
    """Serialize a single PDNGame to a PDN string.

    Emits:
    - Tag pairs in canonical order (Event, Site, Date, Round, White, Black,
      Result, GameType) followed by SetUp/FEN if present, then extras.
    - GameType defaults to Russian 8x8 if not set.
    - Date in YYYY.MM.DD format; bare year converted; unknown → ????.??.??
    - Movetext with move numbers, line-wrapped at ~80 chars.
    - Result token appended after last move.
    """
    lines: list[str] = []

    # Build ordered header
    headers = dict(game.headers)

    # Ensure GameType is set
    if "GameType" not in headers:
        headers["GameType"] = RUSSIAN_DRAUGHTS_GAMETYPE

    # Normalize date
    if "Date" in headers:
        headers["Date"] = _normalize_date(headers["Date"])

    # Emit canonical tags
    emitted: set[str] = set()
    for tag in _CANONICAL_TAGS:
        if tag in headers:
            lines.append(f'[{tag} "{headers[tag]}"]')
            emitted.add(tag)
        elif tag == "GameType":
            # Always emit GameType
            lines.append(f'[{tag} "{RUSSIAN_DRAUGHTS_GAMETYPE}"]')
            emitted.add(tag)

    # SetUp / FEN (in that order)
    for tag in _SETUP_TAGS:
        if tag in headers:
            lines.append(f'[{tag} "{headers[tag]}"]')
            emitted.add(tag)

    # Any remaining extra tags
    for tag, value in headers.items():
        if tag not in emitted:
            lines.append(f'[{tag} "{value}"]')

    lines.append("")

    # Build movetext. If a tree is present and has variations (or
    # annotations on move nodes), render it as RAV; otherwise fall back
    # to the flat move-list format for byte-identical output to pre-M5
    # files. Determine starting side-to-move from the FEN header, if any:
    # games opened from a black-to-move setup start with "N...".
    result_token = game.result
    tree = game.tree
    starts_with_black = False
    if headers.get("SetUp") == "1":
        fen = headers.get("FEN", "").strip()
        if fen and fen.split(":", 1)[0].strip().upper() == "B":
            starts_with_black = True
    start_ply = 1 if starts_with_black else 0

    # Only move nodes (children of root) matter for the "has_tree_data"
    # test — root-level comments/NAGs are not emitted by _emit_tree_line,
    # so treating them as tree data would create a round-trip asymmetry.
    has_tree_data = tree is not None and (
        tree.has_variations() or any((n.comment or n.nag) for n in tree.root.iter_all() if n is not tree.root)
    )
    if has_tree_data:
        assert tree is not None  # narrowed by has_tree_data
        move_parts: list[str] = []
        _emit_tree_line(
            tree.root,
            move_parts,
            cur_ply=start_ply,
            black_ellipsis=starts_with_black,
        )
        move_parts.append(result_token)
    else:
        move_parts = []
        for i, move in enumerate(game.moves):
            absolute_ply = start_ply + i
            if absolute_ply % 2 == 0:
                move_parts.append(f"{absolute_ply // 2 + 1}.")
            elif i == 0:
                # First move is black's — emit "N..." before it.
                move_parts.append(f"{absolute_ply // 2 + 1}...")
            move_parts.append(move)
        move_parts.append(result_token)

    movetext = " ".join(move_parts)
    # Wrap at ~80 chars, but don't break tokens
    wrapped = _wrap_movetext(movetext, width=80)
    lines.extend(wrapped)
    lines.append("")

    return "\n".join(lines)


def _escape_pdn_comment(text: str) -> str:
    """Make ``text`` safe to wrap inside ``{...}`` in PDN.

    PDN has no comment-escape convention; most tools reject unmatched
    braces. We replace both opening and closing braces with square brackets
    so the output round-trips through our parser and is accepted by
    third-party tools.
    """
    return text.replace("{", "[").replace("}", "]")


def _emit_tree_line(
    node: GameNode,
    parts: list[str],
    cur_ply: int,
    black_ellipsis: bool,
) -> None:
    """Emit the descendants of ``node`` as PDN movetext (with RAV).

    - ``cur_ply`` is the absolute ply index of the NEXT move to emit
      (0 = white's 1st move, 1 = black's 1st, ...).
    - ``black_ellipsis=True`` means the first emitted move (if it is
      black's) needs an ``N...`` prefix — used at the start of a
      variation whose first move is black.
    """
    cur = node
    first = True
    while cur.children:
        main = cur.children[0]
        # Move number
        if cur_ply % 2 == 0:
            parts.append(f"{cur_ply // 2 + 1}.")
        elif first and black_ellipsis:
            parts.append(f"{cur_ply // 2 + 1}...")
        first = False
        # Move + NAGs + comment
        assert main.move is not None
        parts.append(main.move)
        for ng in main.nag:
            parts.append(NAG_REVERSE.get(ng, ng))
        if main.comment:
            parts.append("{" + _escape_pdn_comment(main.comment) + "}")
        # Alternative variations (siblings after main) — each in its own parens
        for var in cur.children[1:]:
            parts.append("(")
            # The variation's first move sits at the same ply as ``main``.
            if cur_ply % 2 == 0:
                parts.append(f"{cur_ply // 2 + 1}.")
            else:
                parts.append(f"{cur_ply // 2 + 1}...")
            assert var.move is not None
            parts.append(var.move)
            for ng in var.nag:
                parts.append(NAG_REVERSE.get(ng, ng))
            if var.comment:
                parts.append("{" + _escape_pdn_comment(var.comment) + "}")
            _emit_tree_line(var, parts, cur_ply + 1, black_ellipsis=True)
            parts.append(")")
        cur = main
        cur_ply += 1


def _normalize_date(d: str) -> str:
    """Normalize a date string to YYYY.MM.DD format.

    Accepts:
      '1949'          → '1949.??.??'
      '1949.01.15'    → '1949.01.15'
      '?'             → '????.??.??'
      '????.??.??'    → '????.??.??'
    """
    if not d or d in ("?", "??", "???"):
        return "????.??.??"
    # Already in correct format
    if re.match(r"^\d{4}\.\d{2}\.\d{2}$", d):
        return d
    if re.match(r"^\d{4}\.\?+\.\?+$", d):
        return d
    # Bare year
    if re.match(r"^\d{4}$", d):
        return f"{d}.??.??"
    # date with dashes
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", d)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "????.??.??"


def _wrap_movetext(text: str, width: int = 80) -> list[str]:
    """Wrap movetext at word boundaries to stay within `width` chars per line."""
    tokens = text.split()
    lines: list[str] = []
    current = ""
    for token in tokens:
        if not current:
            current = token
        elif len(current) + 1 + len(token) <= width:
            current += " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def write_pdn(games: list[PDNGame], path: str | Path | None = None) -> str:
    """Write games to PDN 3.0 format.

    If path is given, writes to file. Always returns PDN string.
    Replaces the old minimal writer with full canonical output.
    """
    parts = [pdngame_to_string(g) for g in games]
    text = "\n".join(parts)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    return text


def write_pdn_file(games: list[PDNGame], path: str | Path) -> None:
    """Write games to a PDN file (convenience wrapper)."""
    write_pdn(games, path)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r'\[(\w+)\s+"([^"]*)"\]')
_MOVE_NUM_RE = re.compile(r"\d+\.\s*")


def parse_pdn(text: str) -> list[PDNGame]:
    """Parse PDN text into list of games.

    Handles multi-game files. Supports standard PDN headers and move text.
    Accepts both numeric (22-17, 11x18) and algebraic (c3-d4, f6:d4) notation.
    Algebraic moves are stored as-is; numeric moves are stored as-is.
    """
    games: list[PDNGame] = []
    current_headers: dict[str, str] = {}
    move_text = ""
    in_moves = False

    for raw_line in text.split("\n"):
        line = raw_line.strip()

        if not line or line.startswith("%"):
            # Blank line after moves signals end of game
            if in_moves and move_text.strip():
                game = _build_game(current_headers, move_text)
                games.append(game)
                current_headers = {}
                move_text = ""
                in_moves = False
            continue

        header_match = _HEADER_RE.match(line)
        if header_match:
            if in_moves and move_text.strip():
                # New headers after moves = new game
                game = _build_game(current_headers, move_text)
                games.append(game)
                current_headers = {}
                move_text = ""
                in_moves = False
            current_headers[header_match.group(1)] = header_match.group(2)
            continue

        # Must be move text
        in_moves = True
        move_text += " " + line

    # Last game
    if move_text.strip():
        game = _build_game(current_headers, move_text)
        games.append(game)

    return games


# --- RAV-aware tokenizer / parser (M5) -----------------------------------

_MOVE_RE = re.compile(r"^(?:\d+[x\-](?:\d+[x\-])*\d+|[a-h][1-8](?::[a-h][1-8])+|[a-h][1-8]-[a-h][1-8])$")
_MOVENUM_RE = re.compile(r"^\d+\.+$")


def _tokenize_pdn_movetext(text: str) -> list[tuple[str, str]]:
    """Tokenize PDN movetext, respecting {comments}, (variations), and NAGs.

    Returns a list of (kind, value) pairs. Kinds:
      'move', 'nag', 'comment', 'lparen', 'rparen', 'movenum', 'result'.
    Unknown tokens are silently dropped.
    """
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == "{":
            # Comment; terminated by the next '}'. If unbalanced, consume to EOL.
            j = text.find("}", i + 1)
            if j == -1:
                j = n
            tokens.append(("comment", text[i + 1 : j]))
            i = j + 1
            continue
        if c == "(":
            tokens.append(("lparen", "("))
            i += 1
            continue
        if c == ")":
            tokens.append(("rparen", ")"))
            i += 1
            continue
        if c in "!?":
            j = i
            while j < n and text[j] in "!?":
                j += 1
            tokens.append(("nag", text[i:j]))
            i = j
            continue
        if c == "$":
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            tokens.append(("nag", text[i:j]))
            i = j
            continue
        # Regular word — up to next whitespace/paren/brace/NAG-char.
        # NAG glyphs (!?$) stop a word, so '22-17!' splits into '22-17' + '!'.
        j = i
        while j < n and text[j] not in " \t\n\r()[]{}!?$":
            j += 1
        word = text[i:j]
        i = j
        if not word:
            continue
        if _MOVENUM_RE.match(word):
            tokens.append(("movenum", word))
        elif word in _RESULT_TOKENS:
            tokens.append(("result", word))
        elif _MOVE_RE.match(word):
            tokens.append(("move", word))
        # else: unknown punctuation or stray char — drop.
    return tokens


def _parse_tokens_into_tree(
    tokens: list[tuple[str, str]],
    idx: int,
    attach_to: GameNode,
    *,
    in_variation: bool = False,
) -> int:
    """Recursive descent: consume tokens starting at idx, extending the tree.

    Moves go as first-children along a spine; parenthesised variations
    attach as siblings of the move they follow. Returns the index of the
    first unconsumed token (at or past a matching ')' if called from a
    variation, else len(tokens)).

    Stray ``)`` at the top level (``in_variation=False``) is skipped
    instead of truncating the parse — otherwise a single malformed
    paren in the input would silently drop every move after it.
    """
    cur = attach_to  # where the NEXT sequential move attaches
    last_node: GameNode | None = None  # most recently added move node
    while idx < len(tokens):
        kind, val = tokens[idx]
        if kind == "rparen":
            if in_variation:
                return idx + 1
            # Top-level stray ')' — skip without terminating the parse.
            idx += 1
            continue
        if kind == "lparen":
            # Variation attaches to the parent of the last-added move.
            # If no move has been added yet in this scope, skip the
            # variation cleanly to avoid corrupting the tree.
            if last_node is None or last_node.parent is None:
                idx = _skip_balanced_parens(tokens, idx)
                continue
            idx = _parse_tokens_into_tree(tokens, idx + 1, last_node.parent, in_variation=True)
            continue
        if kind == "move":
            last_node = cur.add_child(val)
            cur = last_node
            idx += 1
            continue
        if kind == "nag":
            if last_node is not None:
                last_node.nag.append(NAG_MAP.get(val, val))
            idx += 1
            continue
        if kind == "comment":
            if last_node is not None:
                stripped = val.strip()
                last_node.comment = f"{last_node.comment} {stripped}".strip() if last_node.comment else stripped
            idx += 1
            continue
        # movenum / result / anything else — advance silently
        idx += 1
    return idx


def _skip_balanced_parens(tokens: list[tuple[str, str]], idx: int) -> int:
    """Skip from an opening '(' to its matching ')'. Returns index past ')'."""
    depth = 0
    while idx < len(tokens):
        kind, _ = tokens[idx]
        if kind == "lparen":
            depth += 1
        elif kind == "rparen":
            depth -= 1
            if depth == 0:
                return idx + 1
        idx += 1
    return idx


def _build_game(headers: dict[str, str], move_text: str) -> PDNGame:
    """Build a PDNGame from headers and raw move text, with RAV support."""
    tokens = _tokenize_pdn_movetext(move_text)
    tree = GameTree()
    _parse_tokens_into_tree(tokens, 0, tree.root)
    moves = tree.main_line
    return PDNGame(headers=dict(headers), moves=moves, tree=tree)


def load_pdn_file(path: str | Path) -> list[PDNGame]:
    """Load games from a PDN file."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_pdn(text)


# ---------------------------------------------------------------------------
# Legacy JSON → PDN converter (D2 migration helper)
# ---------------------------------------------------------------------------


def json_to_pdn(json_path: str | Path, pdn_path: str | Path) -> None:
    """Convert a JSON save file to PDN format.

    Loads a JSON game save, reconstructs board positions, infers moves
    between consecutive positions, and writes a PDN file.

    This is the one-time migration function referenced in D2.
    The resulting PDN uses numeric square notation (1-32).
    """
    from draughts.game.board import Board
    from draughts.game.save import load_game

    gs = load_game(json_path)
    positions = gs.positions
    if len(positions) < 2:
        # Write a minimal PDN with no moves
        game = PDNGame(
            headers={
                "Event": "?",
                "Site": "?",
                "Date": _today_date_str(),
                "Round": "?",
                "White": "?",
                "Black": "?",
                "Result": "*",
                "GameType": RUSSIAN_DRAUGHTS_GAMETYPE,
            },
            moves=[],
        )
        write_pdn([game], pdn_path)
        return

    # Reconstruct moves from consecutive board states
    moves: list[str] = []
    for i in range(len(positions) - 1):
        board_before = Board()
        board_before.load_from_position_string(positions[i])
        board_after = Board()
        board_after.load_from_position_string(positions[i + 1])
        move = _infer_pdn_move(board_before, board_after)
        if move:
            moves.append(move)

    # Determine result from final position
    result = _infer_result_from_position(positions[-1])

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
    )
    write_pdn([game], pdn_path)


def _today_date_str() -> str:
    """Return today's date in YYYY.MM.DD format."""
    d = date.today()
    return f"{d.year:04d}.{d.month:02d}.{d.day:02d}"


def _infer_pdn_move(before: Board, after: Board) -> str | None:
    """Try to infer the PDN numeric move between two board states.

    Returns a PDN move string like '22-17' or '11x18' or None if inference fails.
    This is best-effort for migration purposes.
    """
    import numpy as np

    # Find squares that changed
    diff = before.grid != after.grid
    changed_yx = list(zip(*np.where(diff), strict=False))

    if not changed_yx:
        return None

    # Find source (piece disappeared) and dest (piece appeared from empty/different)
    sources = []
    dests = []
    for y, x in changed_yx:
        b_piece = int(before.grid[y, x])
        a_piece = int(after.grid[y, x])
        if b_piece != 0 and a_piece == 0:
            sources.append((x, y))
        elif (b_piece == 0 and a_piece != 0) or (b_piece != 0 and a_piece != 0 and abs(b_piece) != abs(a_piece)):
            dests.append((x, y))

    if len(sources) == 1 and len(dests) == 1:
        sx, sy = sources[0]
        tx, ty = dests[0]
        try:
            src_sq = xy_to_square(sx, sy)
            dst_sq = xy_to_square(tx, ty)
        except ValueError:
            return None
        # Detect capture: if more than 2 cells changed, it was a capture
        is_capture = len(changed_yx) > 2
        sep = "x" if is_capture else "-"
        return f"{src_sq}{sep}{dst_sq}"

    return None


def _infer_result_from_position(pos_str: str) -> str:
    """Best-effort result inference from final position string."""
    has_black = "b" in pos_str or "B" in pos_str
    has_white = "w" in pos_str or "W" in pos_str
    if has_black and not has_white:
        return "0-1"
    if has_white and not has_black:
        return "1-0"
    return "*"
