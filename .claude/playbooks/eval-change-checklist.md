# Checklist: What to verify after changing eval weights

**When to use:** After Texel tuning, manual weight adjustment, or any
change to `_KING_VALUE`, `_PAWN_VALUE`, or other eval constants in
`draughts/game/ai/eval.py`.

## Why this exists

BUG-002 (CRITICAL): Texel tuning changed `_PAWN_VALUE` from 5.0 to
1.9 but annotation thresholds stayed at 50/150/400 (designed for the
old scale). The game analyzer never annotated any move. Feature was
completely broken. Nobody noticed until QA audit.

## Checklist

### 1. Annotation thresholds
**File:** `draughts/ui/game_analyzer.py`
**Constants:** `_INACCURACY_MIN`, `_MISTAKE_MIN`, `_BLUNDER_MIN`
**Check:** Are thresholds reasonable in terms of the NEW pawn value?
  - Inaccuracy ≈ 0.25-0.5 pawns
  - Mistake ≈ 0.75-1.5 pawns
  - Blunder ≈ 2+ pawns
**Formula:** `threshold = desired_pawns * _PAWN_VALUE * 100` (if in cp)
  or just raw eval units if not centipawn.

### 2. Puzzle miner thresholds
**File:** `draughts/game/puzzle_miner.py`
**Constants:** `min_delta_cp` parameter (default 400 in old scale)
**Check:** Does the minimum delta for mining a puzzle still make sense?

### 3. Contempt factor
**File:** `draughts/game/ai/eval.py` → `_CONTEMPT`
**Check:** Is contempt still small relative to pawn value? Should be
  ~5-10% of a pawn at most. If pawn=1.9, contempt should be ~0.1-0.2.
  Currently 0.5 (26% of a pawn) — borderline aggressive.

### 4. Move ordering priorities
**File:** `draughts/game/ai/moves.py` → `_order_moves`
**Constants:** capture priority (100+), promotion priority (50),
  king approach bonus (30+), center bonus scaling
**Check:** Are these still well-separated? If king_value dropped from
  15 to 5.7, does capturing a king still sort higher than a promotion?

### 5. Blunder detection in self-play analysis
**File:** `.planning/bench.py`, heartbeat analysis scripts
**Constants:** "blunder > 3", "big blunder > 10"
**Check:** With new eval scale, is "3" still meaningful? One pawn =
  1.9 now, so a 3-unit swing = 1.5 pawns — still a real blunder.

### 6. Quiescence stand-pat
**File:** `draughts/game/ai/search.py` → `_quiescence`
**Check:** Stand-pat uses `_evaluate_fast`. If the scale compressed,
  quiescence cutoffs (alpha/beta comparisons) still work correctly
  because they're relative. No action needed — but verify.

### 7. Endgame detection
**File:** `draughts/game/ai/eval.py` → `_is_drawn_endgame`
**Check:** Does it use piece VALUES or piece COUNTS? If counts →
  safe. If values → may need recalibration.

### 8. Tests with hardcoded eval expectations
```bash
grep -rn "score.*>" tests/ | grep -v "xfail\|skip"
grep -rn "assert.*eval\|assert.*score" tests/
```
**Check:** Any test asserting `score > 10` when king_value is now 5.7?

### 9. Head-to-head verification
**Always run after weight changes:**
```bash
cp draughts/game/ai/eval.py .planning/ai_old_eval.py
# ... make changes ...
PYTHONPATH=. python .planning/sprt.py --elo0 0 --elo1 10 --max 200
```

### 10. Perf baseline
Weight changes shouldn't affect speed, but verify:
```bash
PYTHONPATH=. python .planning/perf_baseline.py
```
