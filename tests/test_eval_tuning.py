"""Tests for D11 — Texel eval tuning infrastructure.

Covers:
    1. test_feature_extraction_shape    — feature vector has correct length
    2. test_sigmoid_boundaries          — sigmoid(0)=0.5, sigmoid(+large)≈1
    3. test_loss_function_perfect       — predicted==actual → loss≈0
    4. test_load_tuned_weights_fallback — missing file → hand-tuned defaults kept
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_initial_grid() -> np.ndarray:
    """Return the standard opening position as an 8x8 int8 numpy array."""
    from draughts.game.board import Board

    board = Board()
    return board.grid.copy()


# ---------------------------------------------------------------------------
# 1. Feature extraction shape
# ---------------------------------------------------------------------------


def test_feature_extraction_shape() -> None:
    """Feature vector must have exactly _N_FEATURES elements for any position."""
    from draughts.tools.tune_eval import _N_FEATURES, extract_features

    grid = _make_initial_grid()
    feats = extract_features(grid)

    assert feats.shape == (_N_FEATURES,), (
        f"Expected shape ({_N_FEATURES},), got {feats.shape}"
    )
    # All features must be finite (no NaN / Inf)
    assert np.all(np.isfinite(feats)), f"Non-finite features: {feats}"


def test_feature_extraction_symmetry() -> None:
    """Opening position is symmetric: material diff must be 0."""
    from draughts.tools.tune_eval import extract_features

    grid = _make_initial_grid()
    feats = extract_features(grid)

    # feature[0] = material_diff; opening is perfectly balanced
    assert feats[0] == pytest.approx(0.0), (
        f"Expected 0 material diff in opening, got {feats[0]}"
    )


# ---------------------------------------------------------------------------
# 2. Sigmoid boundaries
# ---------------------------------------------------------------------------


def test_sigmoid_boundaries() -> None:
    """sigmoid(0) == 0.5 and sigmoid(large positive) ≈ 1.0."""
    from draughts.tools.tune_eval import sigmoid

    assert sigmoid(0.0) == pytest.approx(0.5)
    assert sigmoid(100.0) == pytest.approx(1.0, abs=1e-6)
    assert sigmoid(-100.0) == pytest.approx(0.0, abs=1e-6)


def test_sigmoid_array() -> None:
    """sigmoid works on numpy arrays and returns values in (0, 1)."""
    from draughts.tools.tune_eval import sigmoid

    xs = np.linspace(-10, 10, 100)
    ys = sigmoid(xs)
    assert ys.shape == xs.shape
    assert np.all(ys > 0.0)
    assert np.all(ys < 1.0)


# ---------------------------------------------------------------------------
# 3. Loss function: perfect predictions → near-zero loss
# ---------------------------------------------------------------------------


def test_loss_function_perfect() -> None:
    """If the model predicts the exact target for every sample, MSE ≈ 0."""
    from draughts.tools.tune_eval import _K, mse_loss, sigmoid

    n = 50
    rng = np.random.default_rng(42)
    # Random features
    features = rng.standard_normal((n, 8))
    weights = rng.standard_normal(8)

    # Compute "perfect" targets = sigmoid(K * features @ weights)
    evals = features @ weights
    results = sigmoid(_K * evals)

    loss = mse_loss(weights, features, results, k=_K)
    assert loss == pytest.approx(0.0, abs=1e-10), (
        f"Expected near-zero loss for perfect predictions, got {loss}"
    )


def test_loss_function_worst_case() -> None:
    """Inverted predictions produce high MSE (close to 0.25 = max for MSE on [0,1])."""
    from draughts.tools.tune_eval import _K, mse_loss, sigmoid

    n = 100
    rng = np.random.default_rng(0)
    features = rng.standard_normal((n, 8))
    weights = rng.standard_normal(8)

    evals = features @ weights
    results_correct = sigmoid(_K * evals)
    # Flip predictions: use negated weights
    loss_inverted = mse_loss(-weights, features, results_correct, k=_K)

    # Should be measurably higher than near-zero.
    # With K=0.2 the sigmoid is quite flat so "worst case" is still modest —
    # the important thing is it's strictly greater than the perfect-prediction
    # baseline of ~0.
    assert loss_inverted > 0.005, (
        f"Expected higher loss for inverted weights, got {loss_inverted}"
    )


# ---------------------------------------------------------------------------
# 4. load_tuned_weights fallback
# ---------------------------------------------------------------------------


def test_load_tuned_weights_fallback_missing_file() -> None:
    """When no tuned weights file exists, hand-tuned defaults are preserved."""
    import draughts.game.ai.eval as eval_module

    # Save current values
    pv_before = eval_module._PAWN_VALUE  # noqa: SLF001
    kv_before = eval_module._KING_VALUE  # noqa: SLF001

    # Point at a non-existent path
    result = eval_module.load_tuned_weights(Path("/tmp/nonexistent_weights_12345.json"))

    assert result is False, "Should return False for missing file"
    # Constants must be unchanged
    assert eval_module._PAWN_VALUE == pv_before   # noqa: SLF001
    assert eval_module._KING_VALUE == kv_before   # noqa: SLF001


def test_load_tuned_weights_valid_file() -> None:
    """Valid tuned weights file is loaded and constants are updated."""
    import draughts.game.ai.eval as eval_module

    weights = {
        "pawn_value": 6.0,
        "king_value": 18.0,
        "advance_bonus": 0.20,
        "center_bonus": 0.07,
        "safety_bonus": 0.12,
        "connected_bonus": 0.10,
        "golden_corner": 0.25,
        "king_center_weight": 0.35,
        "king_distance_weight": 0.45,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(weights, f)
        tmp_path = Path(f.name)

    try:
        result = eval_module.load_tuned_weights(tmp_path)
        assert result is True, "Should return True for valid file"
        assert eval_module._PAWN_VALUE == pytest.approx(6.0)   # noqa: SLF001
        assert eval_module._KING_VALUE == pytest.approx(18.0)  # noqa: SLF001
        assert eval_module._ADVANCE_BONUS == pytest.approx(0.20)  # noqa: SLF001
    finally:
        tmp_path.unlink(missing_ok=True)
        # Restore the weights that were active before this test ran.
        # The production tuned_weights.json is auto-loaded at import time,
        # so we reload it (or fall back to hand-tuned defaults if absent).
        eval_module.load_tuned_weights()


def test_load_tuned_weights_malformed_json() -> None:
    """Malformed JSON file is handled gracefully — returns False, defaults kept."""
    import draughts.game.ai.eval as eval_module

    pv_before = eval_module._PAWN_VALUE  # noqa: SLF001

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ not valid json }")
        tmp_path = Path(f.name)

    try:
        result = eval_module.load_tuned_weights(tmp_path)
        assert result is False
        assert eval_module._PAWN_VALUE == pv_before  # noqa: SLF001
    finally:
        tmp_path.unlink(missing_ok=True)
