# QA Bug Report -- DRAUGHTS Deep Audit #2

**Date:** 2026-04-12
**Branch:** dev (178+ commits, 632 tests, 7 themes, 5 agents)
**Auditor:** Claude QA Engineer (Opus 4.6)
**Scope:** Full codebase deep audit -- search, eval, controller, save, theme, game analyzer

---

## Executive summary

Found **12 findings** across 6 subsystems. 3 bugs fixed (1 CRITICAL, 2 HIGH).
The CRITICAL bug silently broke all game saving since the difficulty system was
expanded from 3 to 6 levels -- autosave fails silently on every game because
`GameSave.__post_init__` still validated `difficulty` in range 1-3 while the
system uses 1-6 since the Elo-based difficulty overhaul.

---

## CRITICAL fixes applied

### BUG-009: GameSave rejects difficulty 4-6 -- saves crash, autosave silent fail
**Severity:** CRITICAL
**Location:** `draughts/game/save.py:27`
**Description:** `GameSave.__post_init__` validated `difficulty must be 1-3` but
the current system uses 1-6 (Elo-based levels). The default difficulty is 4.
Every save attempt with the default or higher difficulty raises `ValueError`.
Autosave catches all exceptions (`except Exception: pass`), so the crash is
swallowed silently -- users lose all game progress on crash/close.
**Fix:** Changed validation to `1 <= self.difficulty <= 6`. Updated test.
**Reproduction:**
```python
from draughts.game.save import GameSave
GameSave(difficulty=4, positions=['n'*32], replay_positions=['n'*32])
# ValueError: difficulty must be 1-3, got 4
```

### BUG-010: _is_drawn_endgame returns True for 2K/3K vs 1K (wins, not draws)
**Severity:** HIGH
**Location:** `draughts/game/ai/eval.py:394`
**Description:** The condition `bk >= 1 and wk >= 1` matches any number of kings
on each side. In Russian draughts, 2K vs 1K and 3K vs 1K are wins, not draws.
The engine prematurely returns `-CONTEMPT` at these positions, refusing to search
for the actual winning line. This makes the engine unable to convert 2K vs 1K
endgames -- it plays as if drawn.
**Fix:** Changed to `bk == 1 and wk == 1` (exact 1-vs-1 check).
**Reproduction:**
```python
import numpy as np
from draughts.game.ai.eval import _is_drawn_endgame
grid = np.zeros((8,8), dtype=np.int8)
grid[0, 1] = 2; grid[0, 3] = 2; grid[7, 6] = -2  # 2K vs 1K
_is_drawn_endgame(grid)  # Was True, now correctly False
```

### BUG-011: Game analyzer is_best detection broken (notation mismatch + threshold)
**Severity:** HIGH
**Location:** `draughts/ui/game_analyzer.py:227`
**Description:** Two compounding bugs:
1. `played_notation` uses PDN numeric format (`"22-18"`) while `best_notation`
   uses algebraic format (`"c3-d4"`). String comparison **never matches**.
2. Fallback `delta_cp < 5.0` is ~2.5 pawns with tuned weights -- any move
   within 2.5 pawns of best is marked `"!"` (good). A move losing 2 pawns
   gets annotated as good instead of blunder.
**Fix:** Compare moves by applying both to the board and checking resulting
positions match. Fallback threshold reduced to `_INACCURACY_MIN` (~0.25 pawns).

---

## Unfixed findings

### BUG-012: No 3-fold repetition detection in GUI controller
**Severity:** MEDIUM
**Location:** `draughts/app/controller.py:481` (`_check_game_over`)
**Description:** `_check_game_over` checks only for no-pieces and no-moves.
`HeadlessGame._record_move` tracks `_position_counts` for 3-fold repetition,
but `GameController` has no equivalent. GUI games can cycle indefinitely
through repeating positions without ending. The AI's contempt factor makes
it unlikely but not impossible, especially in king-only endgames.
**Suggested fix:** Add position count tracking to `GameController._finish_player_move`
and `_on_ai_finished_inner`, declare draw on 3-fold.

### UX-001: Analysis pane inline styles stale after theme switch
**Severity:** MEDIUM
**Location:** `draughts/ui/analysis_pane.py:131-205`
**Description:** 32 `setStyleSheet` calls in `_build_ui()` use colors resolved
from the theme at construction time. Switching themes via Options updates the
window-level QSS but inline styles override the cascade, leaving the analysis
pane in the old theme's colors.
**Who it affects:** Anyone who opens analysis pane then switches theme.
**Suggested fix:** Add a `refresh_theme(name)` method that re-resolves
`_tc` and re-applies all inline styles, called from `_on_options`.

### SMELL-001: _BOARD_PX=640 defined in 3 separate files
**Risk:** MEDIUM
**Location:** `main_window.py:77`, `playback.py:61`, `puzzle_widget.py:261`
**What works now:** All three use the same value.
**What will break it:** Changing the board size requires editing 3 files.
**Suggested hardening:** Define `_BOARD_PX` in `draughts/config.py`, import.

### SMELL-002: book.py _path_is_capture misclassifies king quiet moves
**Risk:** LOW (currently zero impact -- no kings in opening book)
**Location:** `draughts/game/ai/book.py:180`
**What works now:** Opening book only stores opening moves (no kings).
**What will break it:** Extending book to midgame positions with king moves.
**Suggested hardening:** Check board state to determine if captures occurred.

### PERF-001: TT flag for min nodes always LOWER instead of EXACT
**Severity:** LOW
**Location:** `draughts/game/ai/search.py:293`
**Current impact:** ~11.5% EXACT rate vs expected ~30-40%. Fewer TT hits
for min nodes means redundant re-searches.
**Root cause:** `beta` is modified during the min branch but not saved.
The condition `value >= beta` is always true for min (since beta was set
to `min(orig_beta, value)`). Should save `orig_beta` and use it.
**Scaling risk:** Higher depths amplify the TT miss rate.
**Measurement:** Depth-4 search shows 11.5% EXACT, 49% LOWER, 39% UPPER.

### PERF-002: _build_root_move_scores re-searches all root moves after each depth
**Severity:** LOW
**Location:** `draughts/game/ai/search.py:304-334`
**Current impact:** Extra work after each completed depth iteration. TT is
warm so most are hits, but still adds ~10-20% overhead.
**Suggested fix:** Build the ranked list incrementally during the root loop
instead of a separate re-sweep.

### DEBT-001: Analysis pane score display says "Mat" at 9000 but max eval is 1000
**Cost:** LOW
**Location:** `draughts/ui/analysis_pane.py:277`
**What was compromised:** Dead code -- the threshold 9000 never triggers since
`_evaluate_fast` returns -1000/+1000 for terminal positions.
**Suggested fix:** Change threshold to ~900 and display "Выигрыш" (win).

### DEBT-002: Save format lacks invert_color field
**Cost:** LOW
**Location:** `draughts/game/save.py` (GameSave dataclass)
**What was compromised:** Save files don't record which side the player was on.
Loading uses current settings, which may differ from when the game was saved.
**Impact if not paid:** Loaded games may assign sides incorrectly if user
changed the invert_color setting between save and load.

### FLAKY-001: Blunder injection seed uses Python hash() -- non-deterministic
**Test:** Not a test flake, but AI behavior at difficulty 1-2 varies across runs.
**Root cause:** `hash(board.to_position_string())` is randomized by default
in Python 3.3+ (PYTHONHASHSEED).
**Fix:** Use `hashlib.md5(pos.encode()).digest()[:8]` or a fixed-seed hash.

---

## Test protocol results

| Protocol | Result |
|----------|--------|
| 3: All non-default settings game | PASS (20 plies) |
| 6: Inline setStyleSheet grep | 32 calls (above 15 tolerance) |
| Mandatory capture enforcement | PASS |
| Promotion during multi-capture | PASS |
| execute_capture_path promotion | PASS |
| Thread safety analysis | PASS (all workers use board.copy()) |
| Full test suite (post-fix) | 632 passed, 10 skipped, 4 xfailed |

---

## Files changed

| File | Change |
|------|--------|
| `draughts/game/save.py` | Fix difficulty validation 1-3 -> 1-6 |
| `draughts/game/ai/eval.py` | Fix _is_drawn_endgame: exact 1K vs 1K only |
| `draughts/ui/game_analyzer.py` | Fix is_best: position comparison + threshold |
| `tests/test_save.py` | Update test for new difficulty range |
