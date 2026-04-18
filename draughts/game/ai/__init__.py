"""draughts.game.ai — AI package for Russian draughts.

Public API (backward-compatible with the former flat ai.py):

    AIMove, AIEngine, computer_move, evaluate_position, adaptive_depth,
    SearchContext, SearchCancelledError, _search_best_move,
    _generate_all_moves, _last_search_score, _tt

All private symbols that external callers (headless.py, tests, dev tools)
previously imported from the flat module are still importable here.
"""

from __future__ import annotations

import importlib.resources
import logging

import draughts.game.ai.state as _state_mod

# --- Opening book (D8) ---
# Loaded once at import time from the bundled resource file.
# Stays None if the resource is absent (dev environment without built book).
from draughts.game.ai.book import OpeningBook as OpeningBook

DEFAULT_BOOK: OpeningBook | None = None


def load_default_book() -> OpeningBook | None:
    """Load the bundled opening book from draughts/resources/opening_book.json.

    Returns the loaded book, or None if the file does not exist.
    Sets the module-level DEFAULT_BOOK.
    """
    global DEFAULT_BOOK
    try:
        # importlib.resources handles both installed packages and editable installs
        ref = importlib.resources.files("draughts.resources").joinpath("opening_book.json")
        with importlib.resources.as_file(ref) as book_path:
            if book_path.exists():
                DEFAULT_BOOK = OpeningBook.load(book_path)
                return DEFAULT_BOOK
    except Exception as exc:
        logging.getLogger(__name__).debug("Could not load default opening book: %s", exc)
    DEFAULT_BOOK = None
    return None


# Attempt to load at import time; failures are silent (no book = normal search)
load_default_book()

# --- Endgame bitbase (D9) ---
# Loaded once at import time from the bundled resource file.
# Stays None if the resource is absent (run draughts/tools/build_bitbase.py to generate).
from draughts.game.ai.bitbase import EndgameBitbase as EndgameBitbase

DEFAULT_BITBASE: EndgameBitbase | None = None


def load_default_bitbase() -> EndgameBitbase | None:
    """Load the bundled or user-downloaded endgame bitbase.

    Probe order (first match wins):
      1. ``%APPDATA%/DRAUGHTS/bitbase/bitbase_4.json.gz`` — user-downloaded
         4-piece base via the D37 downloader.
      2. ``%APPDATA%/DRAUGHTS/bitbase/bitbase_4.json``
      3. ``draughts/resources/bitbase_4.json.gz`` — shipped with the wheel
         (currently absent; reserved for future bundling).
      4. ``draughts/resources/bitbase_4.json``
      5. ``draughts/resources/bitbase_3.json`` — shipped 3-piece default.

    Returns the loaded bitbase or None if nothing is available. Sets
    the module-level ``DEFAULT_BITBASE``.
    """
    global DEFAULT_BITBASE

    # 1-2: user data dir (downloaded 4-piece).
    from pathlib import Path as _Path

    try:
        from draughts.config import get_data_dir

        user_dir = _Path(get_data_dir()) / "bitbase"
    except Exception:
        user_dir = None

    if user_dir is not None and user_dir.is_dir():
        for name in ("bitbase_4.json.gz", "bitbase_4.json"):
            bb_path = user_dir / name
            if bb_path.exists():
                try:
                    DEFAULT_BITBASE = EndgameBitbase.load(bb_path)
                    logging.getLogger(__name__).info("Loaded user bitbase: %s", bb_path)
                    return DEFAULT_BITBASE
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Failed to load user bitbase %s: %s (falling back to shipped)", bb_path, exc
                    )

    # 3-5: shipped resources.
    for name in ("bitbase_4.json.gz", "bitbase_4.json", "bitbase_3.json"):
        try:
            ref = importlib.resources.files("draughts.resources").joinpath(name)
            with importlib.resources.as_file(ref) as bb_path:
                if bb_path.exists():
                    DEFAULT_BITBASE = EndgameBitbase.load(bb_path)
                    return DEFAULT_BITBASE
        except Exception as exc:
            logging.getLogger(__name__).debug("Could not load %s: %s", name, exc)

    DEFAULT_BITBASE = None
    return None


# Attempt to load at import time; failures are silent (no bitbase = normal search)
load_default_bitbase()

# --- eval ---
from draughts.game.ai.eval import (
    _ADVANCE_BONUS as _ADVANCE_BONUS,
)
from draughts.game.ai.eval import (
    _BLACK_ADVANCE as _BLACK_ADVANCE,
)
from draughts.game.ai.eval import (
    _BLACK_ADVANCE_FLAT as _BLACK_ADVANCE_FLAT,
)
from draughts.game.ai.eval import (
    _CENTER_BONUS as _CENTER_BONUS,
)
from draughts.game.ai.eval import (
    _CENTER_FLAT as _CENTER_FLAT,
)
from draughts.game.ai.eval import (
    _CENTER_MASK as _CENTER_MASK,
)
from draughts.game.ai.eval import (
    _CONNECTED_BONUS as _CONNECTED_BONUS,
)
from draughts.game.ai.eval import (
    _CONTEMPT as _CONTEMPT,
)
from draughts.game.ai.eval import (
    _GOLDEN_CORNER as _GOLDEN_CORNER,
)
from draughts.game.ai.eval import (
    _KING_DISTANCE_WEIGHT as _KING_DISTANCE_WEIGHT,
)
from draughts.game.ai.eval import (
    _KING_VALUE as _KING_VALUE,
)
from draughts.game.ai.eval import (
    _LAST as _LAST,
)
from draughts.game.ai.eval import (
    _MOBILITY_WEIGHT as _MOBILITY_WEIGHT,
)
from draughts.game.ai.eval import (
    _OFF_DIAGONAL_PENALTY as _OFF_DIAGONAL_PENALTY,
)
from draughts.game.ai.eval import (
    _PAWN_VALUE as _PAWN_VALUE,
)
from draughts.game.ai.eval import (
    _SAFETY_BONUS as _SAFETY_BONUS,
)
from draughts.game.ai.eval import (
    _THREAT_PENALTY as _THREAT_PENALTY,
)
from draughts.game.ai.eval import (
    _WHITE_ADVANCE as _WHITE_ADVANCE,
)
from draughts.game.ai.eval import (
    _WHITE_ADVANCE_FLAT as _WHITE_ADVANCE_FLAT,
)
from draughts.game.ai.eval import (
    _any_piece_threatened as _any_piece_threatened,
)
from draughts.game.ai.eval import (
    _count_pieces as _count_pieces,
)
from draughts.game.ai.eval import (
    _count_threatened as _count_threatened,
)
from draughts.game.ai.eval import (
    _dangerous_position as _dangerous_position,
)
from draughts.game.ai.eval import (
    _diagonal_distance as _diagonal_distance,
)
from draughts.game.ai.eval import (
    _evaluate_fast as _evaluate_fast,
)
from draughts.game.ai.eval import (
    _find_pieces as _find_pieces,
)
from draughts.game.ai.eval import (
    _has_single_capture_only as _has_single_capture_only,
)
from draughts.game.ai.eval import (
    _is_drawn_endgame as _is_drawn_endgame,
)
from draughts.game.ai.eval import (
    _is_flank_vulnerable as _is_flank_vulnerable,
)
from draughts.game.ai.eval import (
    _is_near_edge_or_ally as _is_near_edge_or_ally,
)
from draughts.game.ai.eval import (
    _is_on_board as _is_on_board,
)
from draughts.game.ai.eval import (
    _is_path_clear as _is_path_clear,
)
from draughts.game.ai.eval import (
    _king_distance_score as _king_distance_score,
)
from draughts.game.ai.eval import (
    _max_diagonal_reach as _max_diagonal_reach,
)
from draughts.game.ai.eval import (
    _opponent as _opponent,
)
from draughts.game.ai.eval import (
    _scan_diagonal as _scan_diagonal,
)
from draughts.game.ai.eval import (
    evaluate_position as evaluate_position,
)

# --- moves ---
from draughts.game.ai.moves import (
    _BLACK_PROMOTE_ROW as _BLACK_PROMOTE_ROW,
)
from draughts.game.ai.moves import (
    _WHITE_PROMOTE_ROW as _WHITE_PROMOTE_ROW,
)
from draughts.game.ai.moves import (
    _apply_move as _apply_move,
)
from draughts.game.ai.moves import (
    _generate_all_moves as _generate_all_moves,
)
from draughts.game.ai.moves import (
    _order_moves as _order_moves,
)

# --- search ---
from draughts.game.ai.search import (
    _DIFFICULTY_DEPTH as _DIFFICULTY_DEPTH,
)
from draughts.game.ai.search import (
    _MAX_QDEPTH as _MAX_QDEPTH,
)
from draughts.game.ai.search import (
    AIEngine as AIEngine,
)
from draughts.game.ai.search import (
    AIMove as AIMove,
)
from draughts.game.ai.search import (
    _alphabeta as _alphabeta,
)
from draughts.game.ai.search import (
    _bitbase_best_move as _bitbase_best_move,
)
from draughts.game.ai.search import (
    _quiescence as _quiescence,
)
from draughts.game.ai.search import (
    _search_best_move as _search_best_move,
)
from draughts.game.ai.search import (
    adaptive_depth as adaptive_depth,
)
from draughts.game.ai.search import (
    computer_move as computer_move,
)

# --- state ---
from draughts.game.ai.state import (
    SearchCancelledError as SearchCancelledError,
)
from draughts.game.ai.state import (
    SearchContext as SearchContext,
)
from draughts.game.ai.state import (
    _default_ctx as _default_ctx,
)
from draughts.game.ai.state import (
    _history_clear as _history_clear,
)
from draughts.game.ai.state import (
    _history_record as _history_record,
)
from draughts.game.ai.state import (
    _history_score as _history_score,
)
from draughts.game.ai.state import (
    _killers_clear as _killers_clear,
)
from draughts.game.ai.state import (
    _record_killer as _record_killer,
)

# _tt is the live dict object (same reference as _default_ctx.tt), so
# callers that do `ai._tt.clear()` mutate the actual TT.
from draughts.game.ai.state import _tt as _tt

# --- tt ---
from draughts.game.ai.tt import (
    _PIECE_TO_ZI as _PIECE_TO_ZI,
)
from draughts.game.ai.tt import (
    _TT_EXACT as _TT_EXACT,
)
from draughts.game.ai.tt import (
    _TT_LOWER as _TT_LOWER,
)
from draughts.game.ai.tt import (
    _TT_MAX as _TT_MAX,
)
from draughts.game.ai.tt import (
    _TT_UPPER as _TT_UPPER,
)
from draughts.game.ai.tt import (
    _ZOBRIST as _ZOBRIST,
)
from draughts.game.ai.tt import (
    _ZOBRIST_SIDE as _ZOBRIST_SIDE,
)
from draughts.game.ai.tt import (
    _tt_probe as _tt_probe,
)
from draughts.game.ai.tt import (
    _tt_store as _tt_store,
)
from draughts.game.ai.tt import (
    _zobrist_hash as _zobrist_hash,
)

# ---------------------------------------------------------------------------
# _last_search_score backward-compatibility proxy
# ---------------------------------------------------------------------------
# This is a scalar float written by _search_best_move into state._last_search_score.
# Callers that do `import draughts.game.ai as ai; ai._last_search_score` need
# to read the *current* value, not the snapshot taken at import time.
# We implement __getattr__ on the package so attribute access is live.


def __getattr__(name: str) -> object:
    if name == "_last_search_score":
        return _state_mod._last_search_score
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
