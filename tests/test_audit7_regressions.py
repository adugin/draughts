"""Regression tests for elite-QA audit #7 findings.

BUG-1   — save_game_as_pdn must write SetUp/FEN for games that did not
          start as White-to-move from the standard setup, otherwise the
          black-first move numbering is lost and a re-load corrupts the
          color alternation.
BUG-2   — AnalysisWorker must honour its time_ms budget and support
          cooperative cancellation; compute_pv must honour a deadline.
SMELL-1 — evaluate_position and _evaluate_fast must agree on the dead
          1K-vs-1K position (search vs analysis eval divergence).
SMELL-2 — load_settings must reject bool for int fields (bool is a
          subclass of int, so isinstance() alone lets it through).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_qt_app = None


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    global _qt_app
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    _qt_app = QApplication.instance() or QApplication(sys.argv)
    yield _qt_app


@pytest.fixture
def controller(monkeypatch):
    from draughts.app.controller import GameController

    monkeypatch.setattr(GameController, "_start_computer_turn", lambda self: None)
    return GameController()


# ---------------------------------------------------------------------------
# BUG-1: PDN round-trip for black-first / non-standard-start games
# ---------------------------------------------------------------------------

_BLACK_FIRST_FEN = "B:W21,22,23,24,25,26,27,28,29,30,31,32:B1,2,3,4,5,6,7,8,9,10,11,12"


def _write_black_first_pdn(path: Path) -> None:
    pdn = f"""[Event "?"]
[Result "*"]
[GameType "25"]
[SetUp "1"]
[FEN "{_BLACK_FIRST_FEN}"]

1... 9-13 2. 23-18 *
"""
    path.write_text(pdn, encoding="utf-8")


def test_black_first_pdn_save_writes_setup_fen(controller, tmp_path):
    """Saving a black-first game must emit SetUp/FEN and 1... numbering."""
    src = tmp_path / "black_first.pdn"
    _write_black_first_pdn(src)
    controller.load_game_from_pdn(str(src))

    out = tmp_path / "roundtrip.pdn"
    controller.save_game_as_pdn(str(out))
    text = out.read_text(encoding="utf-8")

    assert '[SetUp "1"]' in text
    assert '[FEN "B:' in text
    compact = " ".join(text.split())
    assert "1... 9-13" in compact


def test_black_first_pdn_full_roundtrip(controller, tmp_path):
    """load -> save -> load keeps start color and replays every ply."""
    from draughts.config import Color

    src = tmp_path / "black_first.pdn"
    _write_black_first_pdn(src)
    controller.load_game_from_pdn(str(src))
    assert controller._ply_count == 2  # sanity: source replayed fully

    out = tmp_path / "roundtrip.pdn"
    controller.save_game_as_pdn(str(out))

    controller.load_game_from_pdn(str(out))
    assert controller._game_start_color == Color.BLACK
    # Before the fix the reload defaulted to White at ply 0 and the
    # replay stopped on the first (now-illegal) move.
    assert controller._ply_count == 2


def test_standard_game_save_has_no_setup_header(controller, tmp_path):
    """White-first standard games keep byte-stable headers (no SetUp/FEN)."""
    out = tmp_path / "fresh.pdn"
    controller.save_game_as_pdn(str(out))
    text = out.read_text(encoding="utf-8")
    assert "SetUp" not in text
    assert "FEN" not in text


# ---------------------------------------------------------------------------
# BUG-2: AnalysisWorker cancellation + compute_pv deadline
# ---------------------------------------------------------------------------


def test_analysis_worker_cancel_before_run_emits_none(qt_app):
    from draughts.config import Color
    from draughts.game.board import Board
    from draughts.ui.analysis_pane import AnalysisWorker

    worker = AnalysisWorker(Board(), Color.WHITE, time_ms=3000)
    results: list = []
    worker.finished.connect(results.append)
    worker.cancel()
    worker.run()
    assert results == [None]


def test_analysis_worker_cancel_moves_deadline_to_past(qt_app):
    """cancel() must arm the cooperative cancel in _alphabeta."""
    from draughts.config import Color
    from draughts.game.board import Board
    from draughts.ui.analysis_pane import AnalysisWorker

    worker = AnalysisWorker(Board(), Color.WHITE, time_ms=3000)
    worker.cancel()
    assert worker._ctx.deadline is not None
    assert worker._ctx.deadline < time.perf_counter()


def test_analysis_worker_honours_time_budget(qt_app):
    """A tiny time_ms must terminate the worker quickly (was unbounded)."""
    from draughts.config import Color
    from draughts.game.board import Board
    from draughts.ui.analysis_pane import AnalysisWorker

    worker = AnalysisWorker(Board(), Color.WHITE, time_ms=50)
    results: list = []
    worker.finished.connect(results.append)
    t0 = time.perf_counter()
    worker.run()
    elapsed = time.perf_counter() - t0
    assert results and results[0] is not None
    # 50ms search budget + 50ms PV budget + depth-1 guarantee sweeps.
    # Generous CI slack; pre-fix this ran to full adaptive depth.
    assert elapsed < 5.0


def test_compute_pv_expired_deadline_returns_immediately():
    from draughts.game.analysis import compute_pv
    from draughts.game.headless import HeadlessGame

    hg = HeadlessGame(auto_ai=False)
    t0 = time.perf_counter()
    pv = compute_pv(hg, depth=6, pv_length=5, deadline=t0 - 1.0)
    assert pv == []
    assert time.perf_counter() - t0 < 1.0


# ---------------------------------------------------------------------------
# SMELL-1: canonical evals agree on the dead 1K-vs-1K position
# ---------------------------------------------------------------------------


def test_eval_functions_agree_on_dead_1k_vs_1k():
    import numpy as np
    from draughts.config import BLACK_KING, WHITE_KING, Color
    from draughts.game.ai.eval import _evaluate_fast, evaluate_position

    grid = np.zeros((8, 8), dtype=np.int8)
    grid[0, 1] = BLACK_KING
    grid[7, 0] = WHITE_KING

    for color in (Color.BLACK, Color.WHITE):
        assert evaluate_position(grid, color) == _evaluate_fast(grid, color), (
            f"eval divergence on dead position for {color}"
        )


# ---------------------------------------------------------------------------
# SMELL-2: load_settings must reject bool where int is expected
# ---------------------------------------------------------------------------


def test_load_settings_rejects_bool_for_int_fields(tmp_path, monkeypatch):
    import draughts.config as config

    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path)
    (tmp_path / config.SETTINGS_FILENAME).write_text(
        json.dumps(
            {
                "hash_size_mb": True,  # bool masquerading as int — reject
                "difficulty": True,  # same — reject
                "remind": False,  # genuine bool field — accept
                "pause": 1.5,  # float field — accept
            }
        ),
        encoding="utf-8",
    )

    s = config.load_settings()
    assert s.hash_size_mb == 64, "bool must not pass the int filter"
    assert s.difficulty == 3, "bool must not pass the int filter"
    assert s.remind is False
    assert s.pause == 1.5
