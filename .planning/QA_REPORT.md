# QA Bug Report — DRAUGHTS Post-Refactoring Audit

**Date:** 2026-04-11
**Branch:** dev (141 commits, 490 tests, 27 decisions)
**Auditor:** Claude QA Engineer
**Methodology:** Integration seam analysis, data flow tracing, edge case probing

---

## Executive Summary

Found **12 bugs** across 7 subsystems. Three are **CRITICAL** (game freeze,
broken game analysis, broken puzzle mining), two are **HIGH** (settings
flags ignored, puzzle validation too permissive), and the rest are
**MEDIUM/LOW**. The most impactful cluster is the eval-scale mismatch:
when Texel tuning changed `_PAWN_VALUE` from 5.0 to 1.9, the annotation
thresholds in `game_analyzer.py` and `puzzle_miner.py` were not adjusted,
rendering both features non-functional.

---

### BUG-001: Editor cancel freezes game when AI was thinking
**Severity:** CRITICAL
**Location:** draughts/ui/main_window.py:598-611
**Category:** logic
**Description:** When the user enters the board editor while the AI is
thinking (computer's turn), `enter_editor_mode` kills the AI thread.
When the user then cancels editing, `_editor_cancel` restores
`_current_turn` to the computer's color but does NOT call
`_start_computer_turn()`. The game is permanently frozen: the player
cannot click (wrong turn), and no AI thread is running.
**Evidence:**
```python
# _editor_cancel restores state but does not restart AI:
self._controller._current_turn = self._editor_saved_turn
# ... emits board_changed, turn_changed ...
# MISSING: if current_turn == computer_color: _start_computer_turn()
```
**Suggested fix:** After restoring state in `_editor_cancel`, add:
```python
if self._controller._current_turn == self._controller._computer_color:
    self._controller._start_computer_turn()
```

---

### BUG-002: Game analyzer thresholds are miscalibrated for tuned eval scale
**Severity:** CRITICAL
**Location:** draughts/ui/game_analyzer.py:39-41
**Category:** semantic
**Description:** The annotation thresholds (`_INACCURACY_MIN=50`,
`_MISTAKE_MIN=150`, `_BLUNDER_MIN=400`) were designed for an eval scale
where `_PAWN_VALUE=5.0`. After Texel tuning, `_PAWN_VALUE=1.9018`.
A typical game move has eval delta of 0.5-3.0 units. Losing a pawn
yields delta ~2. The inaccuracy threshold at 50 requires losing ~26
pawns worth of eval. **Result: the game analyzer NEVER annotates any
move as inaccuracy, mistake, or blunder in normal play.** The entire
feature is non-functional.
**Evidence:**
```
Ply 0: eval_before=-0.00, eval_after=0.06, search_score=0.12
Ply 1: eval_before=-0.06, eval_after=-0.00, search_score=-0.04
# Normal deltas are 0-3 units. Threshold is 50. Never triggers.
```
**Suggested fix:** Scale thresholds to the new eval range:
```python
_INACCURACY_MIN = 0.5   # ~0.25 pawns (was 50)
_MISTAKE_MIN = 1.5       # ~0.75 pawns (was 150)
_BLUNDER_MIN = 4.0       # ~2 pawns (was 400)
```

---

### BUG-003: Puzzle miner uses wrong turn for solver
**Severity:** CRITICAL
**Location:** draughts/game/puzzle_miner.py:108-111
**Category:** logic
**Description:** `mine_puzzles_from_game` uses `positions[ply]` (the
board BEFORE the blunder) as the puzzle position, and
`ann.best_notation` (the engine's recommendation for the side-to-move
at that ply) as the best move. But it sets `solver_turn` to the
OPPONENT of the blunderer. The position has the blunderer to move,
the best_move is for the blunderer, but the puzzle says the solver is
the opponent. The puzzle will show the correct position with the WRONG
side to move and an impossible best_move.
**Evidence:**
```python
blunderer_turn = _turn_string(ply)           # correct: who blundered
solver_turn = "black" if blunderer_turn == "white" else "white"  # BUG: should be blunderer_turn
```
**Suggested fix:** Change to `solver_turn = blunderer_turn` since the
puzzle asks "what should the blunderer have played?" from the
blunderer's position.

---

### BUG-004: use_tuned_eval, use_opening_book, use_endgame_bitbase settings have no effect
**Severity:** HIGH
**Location:** draughts/config.py:92-96, draughts/game/ai/eval.py:232-234, draughts/game/ai/search.py:527-534
**Category:** integration
**Description:** `GameSettings` defines three boolean flags:
`use_opening_book`, `use_endgame_bitbase`, `use_tuned_eval`. None of
these are checked anywhere in the codebase. Tuned weights are loaded
unconditionally at module import time. The opening book and bitbase
are always used if available. The user cannot disable these features
through settings despite the UI suggesting they can.
**Evidence:**
```bash
$ grep -r "use_opening_book\|use_endgame_bitbase\|use_tuned_eval" draughts/ --include="*.py" -l
draughts/config.py    # only defined here, never checked
```
**Suggested fix:** Check these settings in `AIEngine.find_move()`:
```python
if self._book is not None and settings.use_opening_book:
    book_move = self._book.probe(board, self.color)
```
And in `eval.py`, gate `load_tuned_weights()` on the setting.

---

### BUG-005: Puzzle trainer accepts wrong captures as correct
**Severity:** HIGH
**Location:** draughts/ui/puzzle_widget.py:591-609
**Category:** semantic
**Description:** The equivalent 2-square capture validation only checks
that both moves start from the same square and go in the same diagonal
direction. It does NOT verify they capture the same piece. If a position
has two enemy pieces on the same diagonal, the validator will accept a
capture of the wrong piece as correct.
**Evidence:**
```python
# Only checks direction match, not which piece is captured:
if (dx_u > 0) == (dx_b > 0) and (dy_u > 0) == (dy_b > 0):
    if abs(dx_u) >= 2 and abs(dx_b) >= 2:
        self._on_correct()  # may be wrong piece!
```
**Suggested fix:** Use the already-defined (but unused) `_captured_squares`
function to compare actual captured pieces:
```python
if _captured_squares(path) == _captured_squares(best_path):
    self._on_correct()
```

---

### BUG-006: Analysis pane runs search twice (wasted computation)
**Severity:** MEDIUM
**Location:** draughts/ui/analysis_pane.py:70-101
**Category:** logic
**Description:** `AnalysisWorker.run()` first calls
`engine.find_move_timed()` (which runs a full time-limited search),
then DISCARDS the result and runs `_search_best_move()` again with a
fresh `SearchContext`. The first search is completely wasted — the
analysis pane shows results from the second search only. This makes
analysis take ~2x longer than necessary.
**Evidence:**
```python
engine.find_move_timed(self._board.copy(), self._time_ms)  # result discarded!
# ...
ctx = SearchContext()
best = _search_best_move(self._board, self._color, effective_depth, ctx=ctx)  # 2nd search
```
**Suggested fix:** Remove the `find_move_timed` call and use only the
depth-limited search, or use the timed search result directly.

---

### BUG-007: Engine protocol 'go depth 0' returns no move
**Severity:** MEDIUM
**Location:** draughts/engine/session.py:287-318
**Category:** edge-case
**Description:** `go depth 0` causes the loop `range(1, 0+1)` to be empty,
so `best_move` stays `None` and the engine reports `bestmove (none)` even
when legal moves exist. An external GUI sending `go depth 0` would think
the game is lost.
**Evidence:**
```
> position startpos
> go depth 0
< bestmove (none)
```
**Suggested fix:** Clamp depth to minimum 1:
```python
depth = max(1, depth)
```

---

### BUG-008: Engine protocol 'go infinite' blocks the main thread
**Severity:** MEDIUM
**Location:** draughts/engine/session.py:357-411
**Category:** logic
**Description:** `_go_infinite` creates a worker thread and immediately
calls `self._worker_thread.join()`, blocking the main I/O loop. The
session cannot receive the `stop` command during infinite search because
the readline loop is blocked. The search runs to `_MAX_INFINITE_DEPTH=20`
and then returns. `go infinite` is effectively `go depth 20`.
**Evidence:**
```python
self._worker_thread = threading.Thread(target=worker, daemon=True)
self._worker_thread.start()
# Main thread reads stdin for 'stop'... but actually blocks:
self._worker_thread.join()  # BLOCKS until search completes
```
**Suggested fix:** Don't join immediately; return from `_go_infinite` so
the main `run()` loop can continue reading `stop`. Handle the stop event
asynchronously.

---

### BUG-009: Puzzle miner blunder threshold miscalibrated
**Severity:** MEDIUM
**Location:** draughts/game/puzzle_miner.py:22, :55
**Category:** semantic
**Description:** `_DEFAULT_MIN_DELTA = 400` uses the same broken scale as
game_analyzer thresholds. With `_PAWN_VALUE=1.9`, a delta of 400 requires
losing ~210 pawns worth of eval. No puzzles will ever be mined from
analyzed games. This is a downstream effect of BUG-002.
**Evidence:** Same as BUG-002 — raw eval deltas are typically 0-10 in
normal play, never reaching 400.
**Suggested fix:** Adjust to `_DEFAULT_MIN_DELTA = 4.0` to match the
new eval scale.

---

### BUG-010: Negative CENTER_BONUS and KING_CENTER_WEIGHT from Texel tuning
**Severity:** LOW
**Location:** draughts/resources/tuned_weights.json
**Category:** semantic
**Description:** Texel tuning produced `center_bonus = -0.0752` and
`king_center_weight = -0.9321`. These negative values mean the engine
PENALIZES center control and king centralization — the opposite of
standard draughts strategy. This is likely a tuning artifact from the
small dataset (2780 samples). The engine may play weaker than the
hand-tuned defaults in positions where center control matters.
**Evidence:**
```json
"center_bonus": -0.0752,
"king_center_weight": -0.9321,
```
**Suggested fix:** Either retune with a larger dataset, or clamp these
values to non-negative: `max(0.0, value)`. Since `use_tuned_eval` is
non-functional (BUG-004), the user can't even opt out.

---

### BUG-011: Opening book does not validate mandatory captures
**Severity:** LOW
**Location:** draughts/game/ai/search.py:527-529
**Category:** edge-case
**Description:** `AIEngine.find_move` probes the opening book before
checking if captures are mandatory. The book returns whatever was stored
during self-play. While book moves should always be legal (built from
valid games), there is no defensive validation. A Zobrist hash collision
or corrupted book file could cause the engine to return an illegal move
(a non-capture when captures are mandatory).
**Evidence:**
```python
if self._book is not None:
    book_move = self._book.probe(board, self.color)
    if book_move is not None:
        return book_move  # No validation against mandatory captures
```
**Suggested fix:** After getting book move, verify it's legal:
```python
legal = _generate_all_moves(board, self.color)
if (book_move.kind, book_move.path) in [(k, p) for k, p in legal]:
    return book_move
```

---

### BUG-012: _captured_squares helper defined but never used
**Severity:** LOW
**Location:** draughts/ui/puzzle_widget.py:106-130
**Category:** logic
**Description:** The `_captured_squares` function is defined and
well-documented but never called anywhere. It was clearly intended to
be used in `_validate_move_path` for the equivalent-capture comparison
(see BUG-005), but the actual validation uses a looser direction-based
check instead. This is dead code that should be wired into the validation.
**Evidence:** `grep -r "_captured_squares(" draughts/` returns only the
function definition — no callers.
**Suggested fix:** Wire it into `_validate_move_path` to replace the
overly-permissive direction-based check (fixes BUG-005).

---

## Summary Table

| ID | Severity | Category | Component | Status |
|----|----------|----------|-----------|--------|
| BUG-001 | CRITICAL | logic | main_window / editor | TO FIX |
| BUG-002 | CRITICAL | semantic | game_analyzer | TO FIX |
| BUG-003 | CRITICAL | logic | puzzle_miner | TO FIX |
| BUG-004 | HIGH | integration | config / AI engine | Noted |
| BUG-005 | HIGH | semantic | puzzle_widget | Noted |
| BUG-006 | MEDIUM | logic | analysis_pane | Noted |
| BUG-007 | MEDIUM | edge-case | engine session | Noted |
| BUG-008 | MEDIUM | logic | engine session | Noted |
| BUG-009 | MEDIUM | semantic | puzzle_miner | Downstream of BUG-002 |
| BUG-010 | LOW | semantic | tuned_weights | Noted |
| BUG-011 | LOW | edge-case | opening book | Noted |
| BUG-012 | LOW | logic | puzzle_widget | Dead code |
