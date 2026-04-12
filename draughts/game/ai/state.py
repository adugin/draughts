"""SearchContext — per-search mutable state.

Replaces the former module-level globals (_tt, _killers, _history,
_search_deadline, _last_search_score) with an isolated dataclass so
concurrent HeadlessGame instances (e.g. parallel Tournament games)
cannot interfere with each other's search state.

Module-level names (_default_ctx, _tt, _last_search_score, _killers_clear,
_history_clear) are retained as backward-compatibility shims.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class SearchCancelledError(Exception):
    """Raised inside alpha-beta when the search deadline passes."""


@dataclass
class SearchContext:
    """Isolated mutable state for one alpha-beta search tree."""

    tt: dict[int, tuple[int, float, int, int]] = field(default_factory=dict)
    killers: dict[int, list[tuple[str, tuple]]] = field(default_factory=dict)
    history: dict[tuple, int] = field(default_factory=dict)
    deadline: float | None = None
    last_score: float = float("nan")
    # Scored root moves from the last completed depth iteration.
    # Each entry is (score, kind, path) sorted best-first (descending score).
    # Populated by _search_best_move after each fully completed depth so that
    # callers (e.g. blunder selection in AIEngine.find_move) can inspect the
    # full ranked list without re-running search.
    root_move_scores: list[tuple[float, str, list[tuple[int, int]]]] = field(default_factory=list)

    def clear(self) -> None:
        self.tt.clear()
        self.killers.clear()
        self.history.clear()
        self.last_score = float("nan")
        self.root_move_scores.clear()


# ---------------------------------------------------------------------------
# Module-level default SearchContext and backward-compatibility aliases
# ---------------------------------------------------------------------------
# _default_ctx is the shared module-level context used by _search_best_move
# when no explicit ctx is passed. This replicates the old behaviour where
# _tt, _killers, _history were module-level globals that persisted across
# calls and were shared between any engines in the same process (e.g. both
# sides in a game). When callers want isolation (parallel tournaments,
# tests) they can pass their own SearchContext explicitly.
#
# _last_search_score and _tt are kept as module-level names so existing
# callers (perf_baseline.py, head2head.py, headless.py) that do
# `ai._tt.clear()` or read `_ai._last_search_score` keep working.
# Both are updated by _search_best_move after every call.

_default_ctx: SearchContext = SearchContext()

# _tt points at the default ctx's tt dict so `ai._tt.clear()` still works.
_tt: dict[int, tuple[int, float, int, int]] = _default_ctx.tt

_last_search_score: float = float("nan")


def _killers_clear() -> None:
    """Backward-compat: clear killers on the default context."""
    _default_ctx.killers.clear()


def _history_clear() -> None:
    """Backward-compat: clear history on the default context."""
    _default_ctx.history.clear()


# ---------------------------------------------------------------------------
# Killer moves helpers (operate on a ctx.killers dict)
# ---------------------------------------------------------------------------


def _record_killer(
    killers: dict[int, list[tuple[str, tuple]]],
    depth: int,
    kind: str,
    path: list,
) -> None:
    key = (kind, tuple(path))
    slot = killers.get(depth)
    if slot is None:
        killers[depth] = [key]
    elif key not in slot:
        slot.insert(0, key)
        if len(slot) > 2:
            slot.pop()


# ---------------------------------------------------------------------------
# History heuristic helpers (operate on a ctx.history dict)
# ---------------------------------------------------------------------------
# Increment is depth*depth so cutoffs near the root (deep subtrees
# eliminated) count more than shallow ones.


def _history_record(
    history: dict[tuple, int],
    kind: str,
    path: list,
    depth: int,
) -> None:
    # Only track quiet moves — captures are already ordered first.
    if kind == "capture":
        return
    key = (kind, tuple(path))
    history[key] = history.get(key, 0) + depth * depth


def _history_score(history: dict[tuple, int], kind: str, path: list) -> int:
    if kind == "capture":
        return 0
    return history.get((kind, tuple(path)), 0)
