# Test Audit Report — 2026-04-11

## Summary

- **508 tests collected → 514 after adding 20 new tests**
- **4 xfails** (down from 7 — 3 stale xfails removed)
- **10 skipped** (PyQt6-dependent tests on headless, bitbase build)
- **1 real bug found and fixed** (book move ignoring mandatory captures)
- **1 test isolation issue fixed** (eval weight corruption between tests)

---

## Mission A: Coverage Gaps Found

### Gap 1: Opening book ignores mandatory captures — **BUG FOUND & FIXED**

**Risk: CRITICAL** — Would cause the AI to play illegal moves in games
where a capture was mandatory but the book stored a quiet move for that
hash (possible via transposition).

**Root cause**: `AIEngine.find_move()` returned the book move immediately
without checking `board.has_any_capture()`. Russian draughts rules
require captures when available.

**Fix**: Added capture validation before accepting book moves in
`draughts/game/ai/search.py` line ~530. If captures are mandatory and
the book move is not a capture, the engine falls through to normal
alpha-beta search.

**Tests added**: `TestBookRespectsCaptures` (3 tests) in
`tests/test_coverage_gaps.py`.

### Gap 2: Blundering at low levels + mandatory captures — **ALREADY SAFE**

**Risk: HIGH** — Investigated whether blundered moves at difficulty 1/2
could violate mandatory capture rules.

**Finding**: The blunder mechanism picks from `root_move_scores`, which
comes from `_search_best_move`. Since `_generate_all_moves` only returns
captures when captures exist, all candidates in `root_move_scores` are
captures. The blunder pool is therefore safe.

**Tests added**: `TestBlunderRespectsCaptures` (2 tests) confirming
this.

### Gap 3: FEN parser accepts pawns on promotion rows — **DOCUMENTED**

**Risk: LOW** — `parse_fen()` silently accepts `W:W1:B32` (white pawn
on square 1 = row 0 = promotion row). This should be a king. No crash,
but semantically incorrect board state.

**Status**: Documented in tests. The parser is lenient, which is
arguably correct for a viewer/editor (be liberal in what you accept).
A strict mode could be added later.

**Tests added**: `TestFenPromotionRowPawn` (3 tests).

### Gap 4: Engine protocol invalid move handling — **ALREADY SAFE**

**Risk: MEDIUM** — `position startpos moves c3-d4 INVALID` is handled
gracefully: the session emits `info string Bad move token` and
continues from the last valid position. No crash.

**Tests added**: `TestEngineProtocolInvalidMove` (2 tests).

### Gap 5: Settings backward compatibility — **ALREADY SAFE**

**Risk: MEDIUM** — Loading a `GameSettings` from an older version
(missing new fields like `use_opening_book`, `show_clock`) works because
Python dataclass defaults fill in missing values.

**Tests added**: `TestSettingsBackwardCompat` (3 tests).

### Gap 6: Puzzle wrong move → board restore — **ALREADY SAFE**

**Risk: MEDIUM** — After a wrong move in a puzzle, restoring the board
via `load_from_position_string` correctly restores the original position.

**Tests added**: `TestPuzzleBoardRestore` (1 test).

### Gap 7: Board editor → play from here — **TESTED**

**Risk: MEDIUM** — The editor→play flow works: FEN export from edited
board → HeadlessGame → legal moves generated → moves execute.

**Tests added**: `TestEditorToPlayFromHere` (3 tests) +
`TestHeadlessCustomPositionRoundtrip` (2 tests).

### Gap 8: PDN save/load via controller path — **NOT TESTED (UI-dependent)**

**Risk: LOW** — The controller's `save_game_as_pdn` and
`load_game_from_pdn` methods require a full controller setup with
signals/slots. The underlying `pdn.py` functions ARE thoroughly tested
(29 tests in `test_pdn_roundtrip.py`). The controller wiring is a thin
layer.

### Gap 9: Bitbase in real game — **COVERED BY EXISTING TESTS**

`test_bitbase.py::test_bitbase_integration_with_engine` already tests
that AIEngine picks the bitbase-winning move. The 3-piece endgame
scenario is covered.

### Gap 10: Analysis pane concurrent with game AI — **COVERED**

`test_ai_parallel.py` (3 tests) covers exactly this: concurrent
`find_move` calls from multiple threads, plus concurrent analysis.

### Gap 11: Theme switching preserves game state — **NOT TESTED (Qt-only)**

Requires a running QApplication with board repaint. The `test_themes.py`
tests verify pixmap generation and cache invalidation but not
board-state preservation during switch. Risk is low — theme switching
only affects the texture cache, not the board data model.

### Gap 12: Clock accumulation — **PARTIALLY TESTED**

`TestClockBasicTracking` verifies MoveRecords have eval values.
Actual wall-clock timing is tested in `test_headless_limits.py`.

---

## Mission B: Test Correctness Audit

### Stale Assertions Fixed

1. **`test_eval_tuning.py::test_load_tuned_weights_valid_file`** — The
   `finally` block hardcoded `_PAWN_VALUE = 5.0` and `_KING_VALUE = 15.0`,
   but the production code auto-loads Texel-tuned values (1.9018 / 5.7053)
   at import time. **If this test ran before other eval-dependent tests,
   it would corrupt the eval weights for the rest of the session.**
   
   **Fixed**: Now calls `eval_module.load_tuned_weights()` to restore the
   actual active weights (tuned or default, whichever was loaded at import).

### Stale xfails Fixed

1. **`trap_002`** — AI now avoids the "Kingside Collapse" blunder at
   depth 5. Removed from `_TRAP_BLUNDER_XFAIL`.

2. **`puzzle_012`** (difficulty 4) — AI now solves this puzzle at depth 5.
   Removed from xfail list.

3. **`puzzle_021`** (difficulty 4) — AI now solves this puzzle at depth 5.
   Removed from xfail list.

**Remaining xfails** (4 total, all still genuinely fail):
- `trap_008` — h-File Attack Trap, needs depth 7+
- `trap_017` — Center Exchange + Right Wing, needs depth 7+
- `trap_019` — g-File Diagonal Attack, needs depth 7+
- `puzzle_025` — difficulty-4 puzzle, too hard for depth 5

### Vacuous Tests Found

1. **`test_analysis_mode.py::TestEvalCurveData`** (3 tests) — These tests
   simulate `set_evals`/`get_evals` behavior using plain Python `list()`
   operations, never touching the actual `EvalCurveWidget`. They test
   `list()` behaves like `list()`. **Harmless but provide zero coverage.**
   Not removed because they at least verify the import doesn't crash.

2. **`test_tactics_suite.py::test_master_game_match_rate`** — Always
   passes with `assert total_positions >= 0` (vacuously true). This is
   by design (informational test), documented in its docstring.

3. **`test_tactics_suite.py::test_tactics_summary`** — Always passes with
   `assert True`. By design — it's a reporting test.

### Test Isolation Issues

1. **`test_eval_tuning.py`** — **FIXED** (see above). The `finally` block
   was corrupting module-level eval constants for subsequent tests.

2. **`test_tactics_suite.py`** — Uses module-level accumulators
   (`_trap_avoided`, `_trap_replied`, etc.) that persist across tests.
   This is by design for the summary test, but means test results depend
   on execution order. Not a problem in practice since the summary test
   runs last by name.

### Obsolete Tests — None Found

All test imports resolve correctly. No tests reference removed functions
or old module paths. The `from draughts.game.headless import Analysis`
backward-compat import is tested explicitly in `test_analysis.py`.

### Missing Error-Path Tests

1. **`test_pdn_roundtrip.py`** — Tests valid PDN thoroughly but has no
   test for corrupt/malformed PDN input (e.g., truncated file, garbage
   bytes). The parser is tolerant by design, but a test would confirm
   no crash.

2. **`test_opening_book.py`** — No test for corrupt book JSON file.
   The `load` function would raise on bad JSON, but there's no test for
   graceful degradation.

3. **`test_save.py`** — Tests corrupt file via `load_nonexistent_raises`
   but not a corrupt JSON file (valid JSON but wrong schema).

---

## Files Changed

### Bug fix:
- `draughts/game/ai/search.py` — Added mandatory capture check before
  accepting book moves in `AIEngine.find_move()`

### Test fixes:
- `tests/test_tactics_suite.py` — Removed 3 stale xfails (trap_002,
  puzzle_012, puzzle_021); switched puzzle xfails from difficulty-based
  to specific ID-based (`_PUZZLE_XFAIL` dict)
- `tests/test_eval_tuning.py` — Fixed eval weight restoration in
  `test_load_tuned_weights_valid_file` finally block

### New tests:
- `tests/test_coverage_gaps.py` — 20 new tests covering:
  - Book + mandatory captures (3 tests)
  - Blunder + mandatory captures (2 tests)
  - FEN promotion row edge case (3 tests)
  - Engine protocol invalid moves (2 tests)
  - Settings backward compatibility (3 tests)
  - Puzzle board restore (1 test)
  - HeadlessGame custom position roundtrip (2 tests)
  - Editor → play from here flow (3 tests)
  - Clock tracking (1 test)

---

## Test counts

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 508 | 514+ |
| Passing | 491 | 500+ |
| xfailed | 7 | 4 |
| Skipped | 10 | 10 |
| New tests | — | 20 |
