"""Tests for bitbase __meta__ roundtrip (HIGH-06)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from draughts.game.ai.bitbase import DRAW, LOSS, WIN, EndgameBitbase


def test_save_load_roundtrip_preserves_max_pieces(tmp_path: Path):
    bb = EndgameBitbase(entries={1: WIN, 2: DRAW, 3: LOSS}, max_pieces=4)
    path = tmp_path / "bb.json"
    bb.save(path)

    loaded = EndgameBitbase.load(path)
    assert loaded.max_pieces == 4
    assert len(loaded) == 3


def test_legacy_file_without_meta_loads_max_pieces_none(tmp_path: Path):
    """Files from the old format (no __meta__) still work — max_pieces = None."""
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"1": 1, "2": 0, "3": -1}), encoding="utf-8")

    loaded = EndgameBitbase.load(legacy)
    assert loaded.max_pieces is None
    assert len(loaded) == 3


def test_meta_not_counted_as_entry(tmp_path: Path):
    bb = EndgameBitbase(entries={1: WIN, 2: DRAW}, max_pieces=3)
    path = tmp_path / "bb.json"
    bb.save(path)
    # The file text has __meta__ plus two numeric keys.
    txt = path.read_text(encoding="utf-8")
    assert "__meta__" in txt
    # Raw dict len = 3 (meta + 2 hashes), but loaded.len == 2.
    loaded = EndgameBitbase.load(path)
    assert len(loaded) == 2


def test_gzip_roundtrip_preserves_max_pieces(tmp_path: Path):
    bb = EndgameBitbase(entries={42: WIN}, max_pieces=4)
    raw_path = tmp_path / "bb.json"
    bb.save(raw_path)
    gz_path = tmp_path / "bb.json.gz"
    with gzip.open(gz_path, "wb") as fh:
        fh.write(raw_path.read_bytes())

    loaded = EndgameBitbase.load(gz_path)
    assert loaded.max_pieces == 4


def test_malformed_meta_is_ignored(tmp_path: Path):
    """Non-dict or non-int max_pieces falls back to None — no crash."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"__meta__": "not-a-dict", "1": 1}),
        encoding="utf-8",
    )
    loaded = EndgameBitbase.load(bad)
    assert loaded.max_pieces is None

    bad2 = tmp_path / "bad2.json"
    bad2.write_text(
        json.dumps({"__meta__": {"max_pieces": "five"}, "1": 1}),
        encoding="utf-8",
    )
    loaded2 = EndgameBitbase.load(bad2)
    assert loaded2.max_pieces is None


def test_max_pieces_out_of_range_rejected(tmp_path: Path):
    """Absurd max_pieces values are silently dropped to None."""
    nonsense = tmp_path / "big.json"
    nonsense.write_text(
        json.dumps({"__meta__": {"max_pieces": 999}, "1": 1}),
        encoding="utf-8",
    )
    loaded = EndgameBitbase.load(nonsense)
    assert loaded.max_pieces is None
