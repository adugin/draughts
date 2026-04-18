"""Tests for configurable TT size (#38)."""

from __future__ import annotations

from draughts.game.ai.state import SearchContext
from draughts.game.ai.tt import _tt_store, tt_entries_for_mb


def test_entries_scale_with_mb():
    small = tt_entries_for_mb(1)
    medium = tt_entries_for_mb(64)
    large = tt_entries_for_mb(256)
    assert small < medium < large


def test_entries_floor_protects_tiny_values():
    # 1 MB -> at least 8K entries per _TT_BYTES_PER_ENTRY=128, floor is 50K.
    assert tt_entries_for_mb(1) >= 50_000
    assert tt_entries_for_mb(0) >= 50_000
    assert tt_entries_for_mb(-5) >= 50_000  # defensive


def test_entries_match_budget_at_normal_sizes():
    # 128 MB at 128 bytes/entry -> exactly 1,048,576 entries.
    assert tt_entries_for_mb(128) == 128 * 1024 * 1024 // 128


def test_searchcontext_default_tt_max():
    ctx = SearchContext()
    assert ctx.tt_max == 500_000


def test_searchcontext_resize_updates_cap():
    ctx = SearchContext()
    ctx.set_tt_size_mb(64)
    assert ctx.tt_max == tt_entries_for_mb(64)


def test_tt_store_respects_custom_tt_max():
    """_tt_store should clear when len(tt) > tt_max, not the 500K default."""
    tt: dict = {}
    # Pre-populate with 100 dummy entries.
    for i in range(100):
        tt[i] = (1, 0.0, 0, 0)
    # Insert one more with tt_max=50 — should trigger clear().
    _tt_store(tt, 999, 1, 0.0, 0, 0, tt_max=50)
    assert tt == {}


def test_tt_store_default_tt_max_backcompat():
    """Without tt_max keyword, default _TT_MAX=500_000 still applies."""
    tt: dict = {}
    # Fill to 100 entries, well under 500K. Next store should NOT clear.
    for i in range(100):
        tt[i] = (1, 0.0, 0, 0)
    _tt_store(tt, 999, 1, 0.0, 0, 0)
    assert 999 in tt
    assert len(tt) == 101


def test_aiengine_passes_hash_size_mb():
    """AIEngine(hash_size_mb=N) should configure the internal ctx."""
    from draughts.config import Color
    from draughts.game.ai import AIEngine

    e = AIEngine(difficulty=1, color=Color.BLACK, use_book=False, use_bitbase=False, hash_size_mb=64)
    assert e._ctx.tt_max == tt_entries_for_mb(64)

    e2 = AIEngine(difficulty=1, color=Color.BLACK, use_book=False, use_bitbase=False)
    # Without the kwarg — default 500_000.
    assert e2._ctx.tt_max == 500_000
