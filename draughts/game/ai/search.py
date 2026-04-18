"""Alpha-beta search, iterative deepening, AIEngine, and top-level wrappers."""

from __future__ import annotations

import hashlib
import random
import time
from typing import TYPE_CHECKING

import draughts.game.ai.state as _state

if TYPE_CHECKING:
    from draughts.game.ai.bitbase import EndgameBitbase
    from draughts.game.ai.book import OpeningBook
from draughts.config import Color
from draughts.game.ai.eval import (
    _CONTEMPT,
    _evaluate_fast,
    _opponent,
)
from draughts.game.ai.moves import (
    _BLACK_PROMOTE_ROW,
    _WHITE_PROMOTE_ROW,
    _apply_move,
    _generate_all_moves,
    _order_moves,
)
from draughts.game.ai.state import (
    SearchCancelledError,
    SearchContext,
    _default_ctx,
    _history_record,
    _record_killer,
)
from draughts.game.ai.tt import (
    _TT_EXACT,
    _TT_LOWER,
    _TT_UPPER,
    _tt_probe,
    _tt_store,
    _zobrist_hash,
)
from draughts.game.board import Board

# Blundering configuration (D7).
# At low Elo levels the AI deliberately picks a non-best move with the
# given probability, chosen from the top-K moves by eval.  This makes
# beginner games winnable with realistic-looking mistakes.
_BLUNDER_CONFIG: dict[int, dict] = {
    1: {"probability": 0.20, "top_k": 5},  # 20% chance, pick from top 5
    2: {"probability": 0.10, "top_k": 4},  # 10% chance, pick from top 4
}

# Difficulty → base search depth mapping.
# Six levels mapped to approximate Elo strength.
# NOTE: Elo numbers are placeholder calibration to be refined by
# self-play tournaments (D6). Initial values are reasonable estimates.
_DIFFICULTY_DEPTH = {
    1: 2,  # ~800 Elo  — Новичок
    2: 3,  # ~1100 Elo — Любитель
    3: 4,  # ~1400 Elo — Клубный
    4: 5,  # ~1700 Elo — Сильный клубный  (was old "normal")
    5: 6,  # ~2000 Elo — Кандидат         (was old "professional")
    6: 8,  # ~2200 Elo — Мастер           (max)
}

# Maximum quiescence depth
_MAX_QDEPTH = 6


# ---------------------------------------------------------------------------
# Move representation
# ---------------------------------------------------------------------------


class AIMove:
    """Result returned by the AI."""

    def __init__(self, kind: str, path: list[tuple[int, int]]):
        self.kind = kind
        self.path = path

    def __repr__(self) -> str:
        return f"AIMove({self.kind!r}, {self.path})"


# ===========================================================================
# QUIESCENCE SEARCH — resolve captures beyond depth limit
# ===========================================================================


def _quiescence(
    board: Board,
    alpha: float,
    beta: float,
    maximizing: bool,
    color: str | Color,
    root_color: str | Color,
    ctx: SearchContext,
    qdepth: int = 0,
) -> float:
    """Search captures *and* promotion moves to tame horizon effects.

    Captures are the classical quiescence set. Promotion moves are added
    because promoting a pawn to a king swings eval by ~10 material points
    (king_value - pawn_value) in a single ply, so leaving them to stand-pat
    causes the same horizon-blindness quiescence was designed to avoid.
    Self-play profiling (Phase 3 analysis) found that 100% of the
    "quiet-move blunders" with eval-swing >3 were uncovered promotions.
    """
    # Fail-SOFT quiescence. Previously this function returned `alpha` or
    # `beta` at cutoffs (fail-hard), which silently clamped sub-tree
    # values to the caller's window. Combined with the fail-soft
    # _alphabeta above, the clamping caused a real bug: at the root,
    # moves whose true value was below the running alpha all got
    # returned as exactly alpha, tying every "worse" move with the
    # running best and feeding a bag of random blunders to
    # random.choice at the end of _search_best_move. Fail-soft lets the
    # actual sub-tree score propagate.
    stand_pat = _evaluate_fast(board.grid, root_color)
    best = stand_pat

    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        if stand_pat > alpha:
            alpha = stand_pat
    else:
        if stand_pat <= alpha:
            return stand_pat
        if stand_pat < beta:
            beta = stand_pat

    if qdepth >= _MAX_QDEPTH:
        return stand_pat

    moves = _generate_all_moves(board, color)
    tactical = []
    promote_row = _BLACK_PROMOTE_ROW if Color(color) == Color.BLACK else _WHITE_PROMOTE_ROW
    for k, p in moves:
        if k == "capture":
            tactical.append((k, p))
        elif k == "move":
            x1, y1 = p[0]
            _x2, y2 = p[-1]
            start_piece = int(board.grid[y1, x1])
            is_pawn = abs(start_piece) == 1
            if is_pawn and y2 == promote_row:
                tactical.append((k, p))
    if not tactical:
        return best

    opp = _opponent(color)

    if maximizing:
        for kind, path in tactical:
            child = _apply_move(board, kind, path)
            score = _quiescence(child, alpha, beta, False, opp, root_color, ctx, qdepth + 1)
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return best
    else:
        for kind, path in tactical:
            child = _apply_move(board, kind, path)
            score = _quiescence(child, alpha, beta, True, opp, root_color, ctx, qdepth + 1)
            if score < best:
                best = score
            if score < beta:
                beta = score
            if alpha >= beta:
                break
        return best


# ===========================================================================
# ALPHA-BETA MINIMAX with TT + killer moves + quiescence
# ===========================================================================


def _alphabeta(
    board: Board,
    depth: int,
    alpha: float,
    beta: float,
    maximizing: bool,
    color: str | Color,
    root_color: str | Color,
    ctx: SearchContext,
    path_hashes: set[int] | None = None,
) -> float:
    """Alpha-beta pruning minimax with TT, quiescence, LMR, and repetition detection."""
    # Cooperative cancellation: check deadline at depths >= 2 (cheap enough,
    # still bounds wall-clock within ~few ms of any sub-tree at depth 2+).
    if depth >= 2 and ctx.deadline is not None and time.perf_counter() >= ctx.deadline:
        raise SearchCancelledError()

    # Quiescence search at leaf nodes
    if depth <= 0:
        return _quiescence(board, alpha, beta, maximizing, color, root_color, ctx)

    # Transposition table probe
    h = _zobrist_hash(board.grid, Color(color))

    # Repetition detection — draw score with contempt bias.
    # Contempt is always a slight negative from root's perspective so the
    # searching side avoids cycles when better continuations exist.
    if path_hashes is not None and h in path_hashes:
        return -_CONTEMPT

    tt_score, tt_best_idx = _tt_probe(ctx.tt, h, depth, alpha, beta)
    if tt_score is not None:
        return tt_score

    moves = _generate_all_moves(board, color)
    if not moves:
        return -1000.0 if maximizing else 1000.0

    # Drawn endgame (1K vs 1K) is handled in _evaluate_fast, which is
    # called by quiescence at leaf nodes. This ensures captures are still
    # searched properly — returning contempt here at internal nodes would
    # blind the AI to captures, causing it to walk into losing positions.

    # Move ordering: TT best move first, then killers, then heuristic
    moves = _order_moves(moves, board, color, ctx.history)

    # Put TT best move first if available
    if 0 <= tt_best_idx < len(moves):
        best = moves.pop(tt_best_idx)
        moves.insert(0, best)

    # Promote killer moves
    killers = ctx.killers.get(depth)
    if killers:
        for ki in range(len(moves) - 1, 0, -1):
            k, p = moves[ki]
            if (k, tuple(p)) in killers:
                moves.insert(1, moves.pop(ki))

    opp = _opponent(color)
    orig_alpha = alpha
    orig_beta = beta
    best_idx = 0

    # Track position for repetition detection
    child_hashes = path_hashes | {h} if path_hashes is not None else {h}

    if maximizing:
        value = -float("inf")
        for i, (kind, path) in enumerate(moves):
            child = _apply_move(board, kind, path)

            # Late Move Reduction: after first 3 moves, reduce depth for non-captures
            if i >= 3 and depth >= 3 and kind != "capture":
                child_val = _alphabeta(child, depth - 2, alpha, beta, False, opp, root_color, ctx, child_hashes)
                if child_val > alpha:
                    child_val = _alphabeta(child, depth - 1, alpha, beta, False, opp, root_color, ctx, child_hashes)
            else:
                child_val = _alphabeta(child, depth - 1, alpha, beta, False, opp, root_color, ctx, child_hashes)

            if child_val > value:
                value = child_val
                best_idx = i
            alpha = max(alpha, value)
            if alpha >= beta:
                _record_killer(ctx.killers, depth, kind, path)
                _history_record(ctx.history, kind, path, depth)
                break
    else:
        value = float("inf")
        for i, (kind, path) in enumerate(moves):
            child = _apply_move(board, kind, path)

            # Late Move Reduction
            if i >= 3 and depth >= 3 and kind != "capture":
                child_val = _alphabeta(child, depth - 2, alpha, beta, True, opp, root_color, ctx, child_hashes)
                if child_val < beta:
                    child_val = _alphabeta(child, depth - 1, alpha, beta, True, opp, root_color, ctx, child_hashes)
            else:
                child_val = _alphabeta(child, depth - 1, alpha, beta, True, opp, root_color, ctx, child_hashes)

            if child_val < value:
                value = child_val
                best_idx = i
            beta = min(beta, value)
            if alpha >= beta:
                _record_killer(ctx.killers, depth, kind, path)
                _history_record(ctx.history, kind, path, depth)
                break

    # Store in transposition table
    if value <= orig_alpha:
        flag = _TT_UPPER
    elif value >= orig_beta:
        flag = _TT_LOWER
    else:
        flag = _TT_EXACT
    _tt_store(ctx.tt, h, depth, value, flag, best_idx, tt_max=ctx.tt_max)

    return value


def _search_best_move(
    board: Board,
    color: str | Color,
    max_depth: int,
    deadline: float | None = None,
    ctx: SearchContext | None = None,
) -> AIMove | None:
    """Iterative deepening search with alpha-beta minimax.

    If deadline (monotonic perf_counter seconds) is set and elapses mid-search,
    returns the best move from the last fully completed depth iteration.
    A depth-1 sweep is always attempted first to guarantee a legal move.

    Also updates module-level _last_search_score with the minimax value
    of the returned move from `color`'s perspective (backward-compat).
    The same value is stored in ctx.last_score for callers using the new API.

    If ctx is None the module-level _default_ctx is used, which replicates
    the old shared-global behaviour (TT persists across all calls in the
    same process, killers/history are reset per call). Pass an explicit
    SearchContext for isolation (e.g. parallel tournament games).

    THREAD SAFETY: _default_ctx is NOT thread-safe. In threaded contexts
    (Qt worker threads, parallel tournaments) every caller MUST pass an
    explicit ctx. Production callers in this codebase (AIEngine,
    AnalysisWorker, analysis.compute_pv, analysis.get_ai_analysis,
    engine.session) all pass explicit ctx — only dev scripts and
    sequential tests still rely on _default_ctx.
    """
    # Use module-level default context when none supplied — matches the old
    # behaviour where _tt / _killers / _history were shared module globals.
    if ctx is None:
        ctx = _default_ctx

    ctx.killers.clear()
    ctx.history.clear()
    ctx.deadline = deadline
    ctx.last_score = float("nan")

    moves = _generate_all_moves(board, color)
    if not moves:
        _state._last_search_score = float("nan")
        return None

    opp = _opponent(color)
    best_kind, best_path = moves[0]
    # Snapshot of the last fully completed depth's best-move set and its
    # backed-up score. Score is from `color`'s (root's) perspective.
    last_complete_best: list[tuple[str, list[tuple[int, int]]]] = [moves[0]]
    last_complete_score: float = float("nan")

    try:
        # Iterative deepening: search at increasing depths
        for depth in range(1, max_depth + 1):
            moves = _order_moves(moves, board, color, ctx.history)

            # Put previous best move first
            for i, (k, p) in enumerate(moves):
                if k == best_kind and p == best_path:
                    if i > 0:
                        moves.insert(0, moves.pop(i))
                    break

            best_score = -float("inf")
            best_moves_at_depth: list[tuple[str, list[tuple[int, int]]]] = []
            depth_scores: list[tuple[float, str, list[tuple[int, int]]]] = []
            alpha = -float("inf")
            beta = float("inf")

            try:
                for kind, path in moves:
                    child = _apply_move(board, kind, path)
                    score = _alphabeta(child, depth - 1, alpha, beta, False, opp, color, ctx)
                    depth_scores.append((score, kind, path))

                    if score > best_score:
                        best_score = score
                        best_moves_at_depth = [(kind, path)]
                        alpha = max(alpha, score)
                    elif score == best_score:
                        best_moves_at_depth.append((kind, path))
            except SearchCancelledError:
                # Discard this partial depth; keep last fully completed result.
                break

            if best_moves_at_depth:
                best_kind, best_path = best_moves_at_depth[0]
                last_complete_best = best_moves_at_depth[:]
                last_complete_score = best_score
                # Record scored root moves for blunder selection (D7).
                # Built incrementally during the root loop above — no
                # separate re-sweep needed (PERF-002).
                depth_scores.sort(key=lambda t: t[0], reverse=True)
                ctx.root_move_scores = depth_scores
    finally:
        ctx.deadline = None

    # Final selection: among moves with the same minimax score from the
    # last fully completed depth, pick deterministically — the first
    # entry after move-ordering (_order_moves is a stable sort so equal-
    # priority moves keep their input order).
    #
    # Historical note: previously this called random.choice on the top-3
    # to add "variety for self-play", but it used the module-level
    # unseeded random, which made repeated searches on the *same
    # position* return different moves. From the user's POV this looks
    # like the AI randomly picks between equivalent captures (e.g. taking
    # 1 piece vs 3 when both evaluate to the same score after counter-
    # captures) and turns undo-replay into a non-repeatable experience.
    # Strong engines (Scan, Kingsrow) are deterministic for the same
    # position; we match that. Self-play variety, if needed, should be
    # injected at a higher level (e.g. randomised opening book) rather
    # than at the search tie-break.
    ctx.last_score = last_complete_score
    _state._last_search_score = last_complete_score  # backward-compat: callers read ai._last_search_score
    if len(last_complete_best) == 1:
        kind, path = last_complete_best[0]
    else:
        ordered = _order_moves(last_complete_best, board, color, ctx.history)
        kind, path = ordered[0]
    return AIMove(kind, path)


# ===========================================================================
# AI ENGINE
# ===========================================================================


class AIEngine:
    """Encapsulates AI search parameters.

    Inner search functions remain module-level for performance
    (no method dispatch overhead in hot paths).

    Each AIEngine instance owns its own SearchContext so that concurrent
    engines (e.g. two sides in a parallel tournament) cannot pollute each
    other's transposition table or killer-move state.  The module-level
    _default_ctx is still used by _search_best_move when no ctx is passed
    (backward compat for direct callers).
    """

    #: Sentinel that means "use DEFAULT_BOOK from the ai package".
    _USE_DEFAULT_BOOK = object()
    #: Sentinel that means "use DEFAULT_BITBASE from the ai package".
    _USE_DEFAULT_BITBASE = object()

    def __init__(
        self,
        difficulty: int = 2,
        color: Color = Color.BLACK,
        search_depth: int = 0,
        book: OpeningBook | None | object = _USE_DEFAULT_BOOK,
        bitbase: EndgameBitbase | None | object = _USE_DEFAULT_BITBASE,
        use_book: bool = True,
        use_bitbase: bool = True,
        hash_size_mb: int | None = None,
    ):
        self.difficulty = difficulty
        self.color = color
        self.search_depth = search_depth  # 0 = auto (derived from difficulty)
        self._ctx = SearchContext()
        if hash_size_mb is not None:
            self._ctx.set_tt_size_mb(hash_size_mb)
        self._use_book: bool = use_book
        self._use_bitbase: bool = use_bitbase

        if book is AIEngine._USE_DEFAULT_BOOK:
            # Lazy import to avoid circular dependency (ai.__init__ imports search)
            import draughts.game.ai as _ai_pkg

            self._book: OpeningBook | None = _ai_pkg.DEFAULT_BOOK
        else:
            self._book = book  # type: ignore[assignment]

        if bitbase is AIEngine._USE_DEFAULT_BITBASE:
            import draughts.game.ai as _ai_pkg2

            self._bitbase: EndgameBitbase | None = _ai_pkg2.DEFAULT_BITBASE
        else:
            self._bitbase = bitbase  # type: ignore[assignment]

    def find_move(self, board: Board, deadline: float | None = None) -> AIMove | None:
        """Find the best move for the current board state.

        Consults the opening book first (O(1) lookup); if a book move is
        found it is returned immediately, bypassing iterative deepening and
        quiescence search entirely.  Pass ``book=None`` to the constructor
        to disable book lookups.

        The instance's SearchContext is cleared at the start of each call so
        that TT entries from previous moves do not bleed into the next game
        (important for parallel tournaments).  Within a single find_move call,
        iterative-deepening reuses the TT as intended.

        Args:
            board: Position to search.
            deadline: Optional absolute monotonic time (time.perf_counter seconds).
                If set and elapsed during search, returns best move from the
                last fully completed iterative-deepening depth. A depth-1
                sweep is always attempted, so a legal move is always returned
                if any exists.
        """
        # Opening book probe — O(1), no eval/search
        # Only use the book move if it respects mandatory captures:
        # Russian draughts requires capturing when possible, so a book
        # move that is a quiet move when captures exist would be illegal.
        if self._use_book and self._book is not None:
            book_move = self._book.probe(board, self.color)
            if book_move is not None:
                captures_mandatory = board.has_any_capture(self.color)
                if not captures_mandatory or book_move.kind == "capture":
                    return book_move
                # Book suggested a quiet move but captures are mandatory —
                # fall through to normal search which always respects captures.

        # Endgame bitbase probe (D9) — O(1) per child, exact WLD result.
        # Threshold follows the loaded bitbase size: 3-piece default, 4-piece
        # when the larger JSON/gz file is present (#27).
        if self._use_bitbase and self._bitbase is not None:
            piece_count = board.count_pieces(Color.BLACK) + board.count_pieces(Color.WHITE)
            # Detect whether a 4-piece bitbase is loaded: size > 500K entries
            # is a reliable proxy (3-piece = 399K; 4-piece ≈ 12.8M).
            bitbase_threshold = 4 if len(self._bitbase) > 1_000_000 else 3
            if piece_count <= bitbase_threshold:
                bb_move = _bitbase_best_move(board, self.color, self._bitbase)
                if bb_move is not None:
                    return bb_move
                # bb_move is None when all children are outside the bitbase
                # (e.g. position was reached from a 4-piece parent and hasn't
                # been generated yet) — fall through to normal search.

        self._ctx.clear()
        base = self.search_depth if self.search_depth > 0 else _DIFFICULTY_DEPTH.get(self.difficulty, 5)
        depth = adaptive_depth(base, board)
        best = _search_best_move(board, self.color, depth, deadline=deadline, ctx=self._ctx)

        # Blunder injection (D7): at low levels, occasionally pick a non-best
        # move from the ranked root list so beginners face winnable mistakes.
        blunder_cfg = _BLUNDER_CONFIG.get(self.difficulty)
        if blunder_cfg is not None and best is not None and self.search_depth == 0:
            prob = blunder_cfg["probability"]
            top_k = blunder_cfg["top_k"]
            # Use a position-derived seed for reproducibility in tests while
            # still producing variety across different board positions.
            seed = int.from_bytes(
                hashlib.md5(board.to_position_string().encode(), usedforsecurity=False).digest()[:8],
                "little",
            )
            rng = random.Random(seed)
            if rng.random() < prob:
                scored = self._ctx.root_move_scores
                # Collect up to top_k candidates, excluding the best move.
                best_key = (best.kind, [tuple(p) for p in best.path])
                candidates: list[tuple[str, list[tuple[int, int]]]] = []
                for _score, kind, path in scored[:top_k]:
                    if (kind, [tuple(p) for p in path]) != best_key:
                        candidates.append((kind, path))
                if candidates:
                    kind, path = rng.choice(candidates)
                    best = AIMove(kind, path)

        return best

    def find_move_timed(self, board: Board, time_ms: int, deadline: float | None = None) -> AIMove | None:
        """Iterative deepening under a time budget (D10 — time-based search).

        Runs search up to a large depth cap; iterative deepening stops when
        the time budget is exhausted (via cooperative SearchCancelledError).
        Returns the best move found when the budget is exhausted.

        Args:
            board: Position to search.
            time_ms: Time budget in milliseconds.
            deadline: Optional external deadline (perf_counter seconds).
                The effective deadline is the earlier of the time_ms budget
                and the supplied deadline.
        """
        budget_deadline = time.perf_counter() + time_ms / 1000.0
        effective_deadline = min(budget_deadline, deadline) if deadline is not None else budget_deadline
        self._ctx.clear()
        return _search_best_move(board, self.color, 16, deadline=effective_deadline, ctx=self._ctx)


def _bitbase_best_move(
    board: Board,
    color: Color,
    bitbase: EndgameBitbase,
) -> AIMove | None:
    """Pick the best move using bitbase probe instead of alpha-beta search.

    Used when piece_count <= 3 and a bitbase is available.  Each legal move
    is applied; the resulting position is probed.  The move leading to the
    best outcome is selected:
        opponent LOSS  → we WIN  (best)
        DRAW           → draw
        opponent WIN   → we LOSS (last resort)

    Ties within the same category are broken by move ordering (captures first,
    then center control) for consistency with the normal search.
    """
    from draughts.game.ai.bitbase import DRAW, LOSS, WIN  # avoid circular at module level

    opp = Color.WHITE if color == Color.BLACK else Color.BLACK
    moves = _generate_all_moves(board, color)
    if not moves:
        return None

    # Score each move from our perspective: opp LOSS=2 (best), DRAW=1, opp WIN=0 (worst), unknown=-1
    score_map = {LOSS: 2, DRAW: 1, WIN: 0}  # opponent's result → our score

    best_score = -1
    best_moves: list[tuple[str, list[tuple[int, int]]]] = []

    for kind, path in moves:
        child = _apply_move(board, kind, path)
        child_h = _zobrist_hash(child.grid, opp)
        opp_result = bitbase.probe_hash(child_h)

        score = -1 if opp_result is None else score_map.get(opp_result, -1)

        if score > best_score:
            best_score = score
            best_moves = [(kind, path)]
        elif score == best_score:
            best_moves.append((kind, path))

    if not best_moves or best_score == -1:
        # All children unknown — fall back to normal search
        return None

    # Tie-break by move ordering
    ordered = _order_moves(best_moves, board, color, None)
    kind, path = ordered[0]
    return AIMove(kind, path)


def adaptive_depth(base_depth: int, board: Board) -> int:
    """Adjust the requested search depth based on piece count.

    - Crowded positions (>16 pieces): cap at 4. Branching is huge and the
      extra plies pay poorly in the opening.
    - Sparse endgames (<=6 pieces): bump by +1 up to a hard cap of 8.

    The endgame boost was +2 until self-play profiling showed that in
    king-heavy endgames (branching factor ~10 per king) the extra ply
    blew up wall-clock budgets and caused ~3% of endgame moves to hit
    the per-move timeout. +1 is the conservative setting; callers that
    want deeper endgame search can pass a larger base_depth explicitly.
    """
    piece_count = board.count_pieces(Color.BLACK) + board.count_pieces(Color.WHITE)
    if piece_count > 16 and base_depth > 4:
        return 4
    if piece_count <= 6 and base_depth < 8:
        return min(base_depth + 1, 8)
    return base_depth


# ===========================================================================
# MAIN ENTRY POINT (backward-compatible wrapper)
# ===========================================================================


def computer_move(
    board: Board,
    difficulty: int = 2,
    color: str | Color = Color.BLACK,
    depth: int | None = None,
) -> AIMove | None:
    """Compute the AI's move.

    Backward-compatible wrapper around AIEngine. Prefer AIEngine for new code.
    """
    engine = AIEngine(difficulty=difficulty, color=Color(color))
    if depth is not None and depth > 0:
        engine.search_depth = depth
    return engine.find_move(board)
