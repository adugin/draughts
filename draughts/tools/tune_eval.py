"""Texel eval tuner for Russian draughts (D11).

Implements the Texel tuning method:
1. Load training data (position_string, result) pairs.
2. For each position extract a feature vector.
3. Fit weights via minimizing MSE of sigmoid(K * dot(features, weights)) vs result.
4. Output optimized weights and save to draughts/resources/tuned_weights.json.

Result convention (from generate_tuning_data.py):
    1.0 = white win, 0.5 = draw, 0.0 = black win

Eval convention: positive = good for BLACK (as in _evaluate_fast).
We convert: white_result = 1 - white_result_from_data ... actually
the sigmoid input should be eval from BLACK's perspective and we
compare to (1 - white_result) = black_result.

Usage:
    python -m draughts.tools.tune_eval
    python -m draughts.tools.tune_eval --data tuning_data.json --output tuned_weights.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Resources directory relative to this file
_RESOURCES = Path(__file__).parent.parent / "resources"
_DEFAULT_DATA = _RESOURCES / "tuning_data.json"
_DEFAULT_OUTPUT = _RESOURCES / "tuned_weights.json"

# Number of features extracted per position
_N_FEATURES = 8

# Texel scaling constant K: maps eval units to sigmoid input.
# With pawn = 5.0 material units, K=0.2 means 5 pawn units → sigmoid(1.0) ≈ 0.73
# which feels right for a decisive material advantage.
_K = 0.2

# Feature names for display
_FEATURE_NAMES = [
    "material_diff",  # (bp*PV + bk*KV) - (wp*PV + wk*KV)
    "advance_diff",  # black pawn advancement - white pawn advancement
    "center_diff",  # black center control - white center control
    "safety_diff",  # back rank safety: black minus white
    "connected_diff",  # connected pawns: black minus white
    "golden_corner_diff",  # corner occupancy: black minus white
    "king_center_diff",  # king centralization: black minus white
    "king_distance_diff",  # king proximity to opponent: black minus white
]

# Default (hand-tuned) weights from eval.py
_DEFAULT_WEIGHTS = {
    "pawn_value": 5.0,
    "king_value": 15.0,
    "advance_bonus": 0.15,
    "center_bonus": 0.05,
    "safety_bonus": 0.1,
    "connected_bonus": 0.08,
    "golden_corner": 0.3,
    "king_center_weight": 0.3,
    "king_distance_weight": 0.4,
}


# ---------------------------------------------------------------------------
# Board constants (duplicated to avoid Qt import chain)
# ---------------------------------------------------------------------------

_BOARD_SIZE = 8
_LAST = _BOARD_SIZE - 1

# Precomputed advancement tables
_BLACK_ADVANCE = np.zeros((_BOARD_SIZE, _BOARD_SIZE), dtype=np.float32)
_WHITE_ADVANCE = np.zeros((_BOARD_SIZE, _BOARD_SIZE), dtype=np.float32)
for _y in range(_BOARD_SIZE):
    for _x in range(_BOARD_SIZE):
        _BLACK_ADVANCE[_y, _x] = _y / _LAST
        _WHITE_ADVANCE[_y, _x] = (_LAST - _y) / _LAST

_BLACK_ADVANCE_FLAT = _BLACK_ADVANCE.ravel().astype(np.float32)
_WHITE_ADVANCE_FLAT = _WHITE_ADVANCE.ravel().astype(np.float32)

# Center mask
_CENTER_MASK = np.zeros((_BOARD_SIZE, _BOARD_SIZE), dtype=np.float32)
for _y in range(_BOARD_SIZE):
    for _x in range(_BOARD_SIZE):
        dist = max(abs(_x - 3.5), abs(_y - 3.5))
        _CENTER_MASK[_y, _x] = max(0.0, (3.5 - dist) / 3.5)
_CENTER_FLAT = _CENTER_MASK.ravel().astype(np.float32)

# Dark squares list: (y, x) pairs where x%2 != y%2
_DARK_SQUARES: list[tuple[int, int]] = []
for _y in range(_BOARD_SIZE):
    for _x in range(_BOARD_SIZE):
        if _x % 2 != _y % 2:
            _DARK_SQUARES.append((_y, _x))

# Character to int8 mapping (matches config.py)
_CHAR_TO_INT: dict[str, int] = {
    "b": 1,  # BLACK
    "B": 2,  # BLACK_KING
    "w": -1,  # WHITE
    "W": -2,  # WHITE_KING
    ".": 0,  # EMPTY
}


def _pos_string_to_grid(pos: str) -> np.ndarray:
    """Convert 32-char position string to 8x8 int8 numpy grid."""
    grid = np.zeros((_BOARD_SIZE, _BOARD_SIZE), dtype=np.int8)
    for idx, (y, x) in enumerate(_DARK_SQUARES):
        grid[y, x] = _CHAR_TO_INT.get(pos[idx], 0)
    return grid


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def extract_features(grid: np.ndarray) -> np.ndarray:
    """Extract the 8-dimensional feature vector from a board grid.

    All features are from BLACK's perspective (positive = good for black).

    Feature vector:
        [0] material_diff       — (bp*PV + bk*KV) - (wp*PV + wk*KV)
                                  Note: raw counts; weights will scale them.
                                  We use unit weights here (PV=1, KV=3 ratio)
                                  and let the optimizer find the scale.
        [1] advance_diff        — sum of black pawn advancement - white pawn advancement
        [2] center_diff         — sum of black center control - white center control
        [3] safety_diff         — back-rank safety (black - white)
        [4] connected_diff      — connected pawns (black - white)
        [5] golden_corner_diff  — corner occupancy (black - white)
        [6] king_center_diff    — king centralization (black - white)
        [7] king_distance_diff  — king proximity (black - white)

    Returns np.ndarray of shape (_N_FEATURES,).
    """
    flat = grid.ravel()
    flat_u8 = flat.view(np.uint8)
    counts = np.bincount(flat_u8, minlength=256)

    black_pawns = int(counts[1])
    black_kings = int(counts[2])
    white_pawns = int(counts[255])  # -1 as uint8
    white_kings = int(counts[254])  # -2 as uint8

    grid_f = flat.astype(np.float32)

    # [0] material: raw piece counts weighted by 5:15 ratio
    material = float(black_pawns * 5.0 + black_kings * 15.0 - white_pawns * 5.0 - white_kings * 15.0)

    # [1] advancement
    bp_mask = grid_f == 1.0
    wp_mask = grid_f == -1.0
    advance = float(np.dot(bp_mask, _BLACK_ADVANCE_FLAT) - np.dot(wp_mask, _WHITE_ADVANCE_FLAT))

    # [2] center control
    black_mask = grid_f > 0
    white_mask = grid_f < 0
    center = float(np.dot(black_mask, _CENTER_FLAT) - np.dot(white_mask, _CENTER_FLAT))

    # [3] back-rank safety
    # Positive if black has pieces on row 0 (their back rank), negative if white on row 7
    black_backrank = float(np.any(grid[0] > 0))  # black's back rank = row 0 (top)
    white_backrank = float(np.any(grid[_LAST] < 0))  # white's back rank = row 7 (bottom)
    # Convention: back rank presence is good for the defender
    safety = white_backrank - black_backrank  # positive = good for black (white defends, black attacks)

    # [4] connected pawns
    conn = 0.0
    if black_pawns > 1 or white_pawns > 1:
        bp = grid[1:, :] == 1
        conn += float(np.count_nonzero(bp[:, 1:] & (grid[:-1, :-1] > 0)))
        conn += float(np.count_nonzero(bp[:, :-1] & (grid[:-1, 1:] > 0)))
        wp = grid[:-1, :] == -1
        conn -= float(np.count_nonzero(wp[:, 1:] & (grid[1:, :-1] < 0)))
        conn -= float(np.count_nonzero(wp[:, :-1] & (grid[1:, 1:] < 0)))

    # [5] golden corners: a1 = grid[7,0], h8 = grid[0,7]
    corner_a1 = float(grid[_LAST, 0])  # positive if black, negative if white
    corner_h8 = float(grid[0, _LAST])
    golden = (1.0 if corner_a1 > 0 else (-1.0 if corner_a1 < 0 else 0.0)) + (
        1.0 if corner_h8 > 0 else (-1.0 if corner_h8 < 0 else 0.0)
    )

    # [6] king centralization
    bk_mask = grid_f == 2.0
    wk_mask = grid_f == -2.0
    king_center = float(np.dot(bk_mask, _CENTER_FLAT) - np.dot(wk_mask, _CENTER_FLAT))

    # [7] king distance to opponent (simplified: count black_kings * opponent_pieces)
    black_kings_pos = np.argwhere(grid == 2)
    white_kings_pos = np.argwhere(grid == -2)
    white_pieces_pos = np.argwhere(grid < 0)
    black_pieces_pos = np.argwhere(grid > 0)

    king_dist = 0.0
    if len(black_kings_pos) > 0 and len(white_pieces_pos) > 0:
        for ky, kx in black_kings_pos:
            min_d = min(max(abs(int(kx - px)), abs(int(ky - py))) for py, px in white_pieces_pos)
            king_dist += max(0.0, 7.0 - min_d)
    if len(white_kings_pos) > 0 and len(black_pieces_pos) > 0:
        for ky, kx in white_kings_pos:
            min_d = min(max(abs(int(kx - px)), abs(int(ky - py))) for py, px in black_pieces_pos)
            king_dist -= max(0.0, 7.0 - min_d)

    return np.array([material, advance, center, safety, conn, golden, king_center, king_dist], dtype=np.float64)


# ---------------------------------------------------------------------------
# Texel loss
# ---------------------------------------------------------------------------


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    """Numerically stable sigmoid."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def mse_loss(
    weights: np.ndarray,
    features: np.ndarray,
    results: np.ndarray,
    k: float = _K,
) -> float:
    """MSE between sigmoid-predicted result and actual game result.

    Args:
        weights: Shape (N_FEATURES,) weight vector.
        features: Shape (n_samples, N_FEATURES) feature matrix.
        results: Shape (n_samples,) target results from BLACK's perspective
                 (1.0 = black win, 0.5 = draw, 0.0 = white win).
        k: Sigmoid scaling constant.

    Returns:
        Mean squared error (scalar).
    """
    evals = features @ weights  # (n_samples,)
    predicted = sigmoid(k * evals)  # (n_samples,)
    errors = predicted - results
    return float(np.mean(errors * errors))


def mse_gradient(
    weights: np.ndarray,
    features: np.ndarray,
    results: np.ndarray,
    k: float = _K,
) -> np.ndarray:
    """Analytical gradient of MSE loss w.r.t. weights."""
    evals = features @ weights
    predicted = sigmoid(k * evals)
    errors = predicted - results
    # d(MSE)/d(w_i) = (2/n) * sum_j(error_j * d(sigma)/d(eval_j) * k * feature_ji)
    # d(sigma)/d(x) = sigma(x) * (1 - sigma(x))
    sigma_deriv = predicted * (1.0 - predicted)
    scale = (2.0 / len(results)) * k
    return scale * (features.T @ (errors * sigma_deriv))


# ---------------------------------------------------------------------------
# Main tuning function
# ---------------------------------------------------------------------------


def tune(
    data: list[dict],
    k: float = _K,
    verbose: bool = True,
) -> dict:
    """Run Texel tuning on the provided training data.

    Args:
        data: List of {"position": str, "result": float} dicts.
              result is from WHITE's perspective (1.0=white wins).
        k: Sigmoid scaling constant.
        verbose: Print progress.

    Returns:
        Dict with optimized weights and metadata.
    """
    try:
        from scipy.optimize import minimize
    except ImportError as e:
        msg = "scipy is required for eval tuning. Install it with: pip install scipy"
        raise ImportError(msg) from e

    n = len(data)
    if verbose:
        print(f"Building feature matrix from {n} positions...")

    # Convert WHITE-perspective results to BLACK-perspective
    # white_result=1.0 → black_result=0.0, white_result=0.0 → black_result=1.0
    features_list = []
    results_black = []

    skipped = 0
    for item in data:
        try:
            grid = _pos_string_to_grid(item["position"])
        except (KeyError, IndexError, ValueError):
            skipped += 1
            continue

        feat = extract_features(grid)
        features_list.append(feat)
        # Convert white-perspective to black-perspective
        results_black.append(1.0 - float(item["result"]))

    if skipped > 0 and verbose:
        print(f"  Skipped {skipped} malformed samples.")

    features = np.array(features_list, dtype=np.float64)  # (n, N_FEATURES)
    results = np.array(results_black, dtype=np.float64)  # (n,)

    if verbose:
        print(f"Feature matrix: {features.shape}, results range: [{results.min():.1f}, {results.max():.1f}]")
        print(
            f"Result distribution: {(results == 0.0).sum()} white wins, "
            f"{(results == 0.5).sum()} draws, {(results == 1.0).sum()} black wins"
        )

    # Initial weights: use current hand-tuned scale factors
    # Each weight multiplies the corresponding feature in the dot product
    # The material feature already has 5:15 baked in, so we start at scale 1.0
    # All other features are already in "bonus units", start at 1.0 scale
    w0 = np.ones(_N_FEATURES, dtype=np.float64)

    loss_before = mse_loss(w0, features, results, k)
    if verbose:
        print(f"\nInitial MSE (unit weights): {loss_before:.6f}")

    # Optimize with L-BFGS-B
    if verbose:
        print("Running L-BFGS-B optimization...")

    result_opt = minimize(
        fun=mse_loss,
        x0=w0,
        args=(features, results, k),
        jac=mse_gradient,
        method="L-BFGS-B",
        options={
            "maxiter": 2000,
            "ftol": 1e-12,
            "gtol": 1e-8,
        },
    )

    w_opt = result_opt.x
    loss_after = mse_loss(w_opt, features, results, k)

    if verbose:
        print(f"Optimized MSE: {loss_after:.6f} (improvement: {loss_before - loss_after:.6f})")
        print(f"Optimization: {result_opt.message}")
        print()
        print("Optimized feature weights:")
        for name, w in zip(_FEATURE_NAMES, w_opt, strict=True):
            print(f"  {name:25s}: {w:+.4f}")

    # Map weights back to eval.py constants.
    # w_opt[i] is a multiplier on feature[i]:
    #   feature[0] = material with PV=5, KV=15 baked in → w_opt[0] scales total material
    #   We extract PV and KV by assuming KV/PV ratio is preserved, and the
    #   overall scale is w_opt[0]:
    #   new_pawn_value = 5.0 * w_opt[0]
    #   new_king_value = 15.0 * w_opt[0]
    pawn_val = 5.0 * float(w_opt[0])
    king_val = 15.0 * float(w_opt[0])

    # Other weights: the feature is already a "raw" quantity (sum of table values),
    # and w_opt[i] acts as the bonus weight directly.
    # advance_diff feature = sum of raw advancement values (not multiplied by bonus yet)
    # → new_advance_bonus = 0.15 * w_opt[1]  (scale from initial hand-tuned)
    advance_bonus = 0.15 * float(w_opt[1])
    center_bonus = 0.05 * float(w_opt[2])
    safety_bonus = 0.1 * float(w_opt[3])
    connected_bonus = 0.08 * float(w_opt[4])
    golden_corner = 0.3 * float(w_opt[5])
    king_center_weight = 0.3 * float(w_opt[6])
    king_distance_weight = 0.4 * float(w_opt[7])

    tuned = {
        "pawn_value": round(pawn_val, 4),
        "king_value": round(king_val, 4),
        "advance_bonus": round(advance_bonus, 4),
        "center_bonus": round(center_bonus, 4),
        "safety_bonus": round(safety_bonus, 4),
        "connected_bonus": round(connected_bonus, 4),
        "golden_corner": round(golden_corner, 4),
        "king_center_weight": round(king_center_weight, 4),
        "king_distance_weight": round(king_distance_weight, 4),
        "_meta": {
            "mse_before": round(loss_before, 8),
            "mse_after": round(loss_after, 8),
            "improvement": round(loss_before - loss_after, 8),
            "n_samples": n,
            "k": k,
            "optimizer": result_opt.message,
        },
    }

    if verbose:
        print()
        print("Translated to eval.py constants:")
        for key, val in tuned.items():
            if key != "_meta":
                print(f"  {key:25s} = {val}")

    return tuned


def main() -> None:
    parser = argparse.ArgumentParser(description="Texel eval tuner for Russian draughts")
    parser.add_argument(
        "--data",
        type=str,
        default=str(_DEFAULT_DATA),
        help=f"Input training data JSON (default: {_DEFAULT_DATA})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(_DEFAULT_OUTPUT),
        help=f"Output tuned weights JSON (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument("--k", type=float, default=_K, help=f"Sigmoid scaling constant K (default: {_K})")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: Training data file not found: {data_path}", file=sys.stderr)
        print("Generate it first with: python -m draughts.tools.generate_tuning_data", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} samples from {data_path}")

    tuned = tune(data, k=args.k, verbose=not args.quiet)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tuned, f, indent=2)

    print(f"\nTuned weights saved to: {out_path}")


if __name__ == "__main__":
    main()
