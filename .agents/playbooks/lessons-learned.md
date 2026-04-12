# Lessons Learned — Anti-patterns and Hard-Won Knowledge

**When to use:** Read before starting any significant work on this
project. These are mistakes we made and want to never repeat.

## Measurement discipline

### "40 games is not enough"
We ran 40-game head-to-head tests and got +53 Elo in one batch,
-53 in the next. Combined 80 games: exactly 50/50. Lesson:
- **60 games minimum** for rough signal (±100 Elo detectable)
- **SPRT with elo0=0 elo1=10** for authoritative verdict
- **Seed bias is real** — always verify by running OLD vs OLD on the
  same seeds before claiming improvement

### "Speed does not equal strength"
History heuristic + smart tiebreak + contempt tuning gave **2.6x
speedup** but **0 Elo gain** in 100-game head-to-head at fixed depth.
Faster search only helps with TIME-based budgets, not DEPTH-based.
- When testing at fixed depth: speed improvement = zero Elo
- When testing at fixed time: speed improvement = more depth = Elo gain
- Always specify which mode you're testing

### "Never commit an improvement without numbers"
Added to CLAUDE.md as a binding rule. The commit message MUST contain
the SPRT/head2head results. If you can't measure it, it's not an
improvement — it's a hope.

## Eval function traps

### "Changing eval scale breaks everything silently"
Texel tuning changed `_PAWN_VALUE` from 5.0 to 1.9. Everything that
used centipawn thresholds (50, 150, 400) became non-functional.
Game analyzer never annotated a single move. Nobody noticed.
- **Rule:** grep for ALL consumers of any changed constant
- **Better rule:** express thresholds in terms of `_PAWN_VALUE`, not
  absolute numbers

### "Hand-tuned weights are wrong in surprising ways"
Texel tuning revealed:
- Center control bonus was NEGATIVE (we were rewarding the wrong thing)
- King centralization in endgame was COUNTER-PRODUCTIVE
- Pawn advancement was 3x more important than we thought
- **Implication:** never trust intuition about eval weights. Measure.

### "Contempt doesn't matter as much as you think"
Changing contempt from 0.25 to 0.5 showed no measurable Elo
difference. The search has bigger problems than draw avoidance.

## Architecture traps

### "Fail-hard + fail-soft = silent catastrophe"
The #1 bug of the project. Quiescence used fail-hard returns
(`return alpha` / `return beta`), alphabeta used fail-soft (`return
value`). Combined: quiescence clamped scores to alpha, all root moves
tied at alpha, `random.choice` picked blunders. **29% blunder rate
was considered normal for MONTHS.**
- **Rule:** ALL search functions must use the SAME convention.
  We chose fail-soft throughout.
- **Detection:** if you see `return alpha` or `return beta` in any
  search function, that's fail-hard. Flag it.

### "Module-level mutable state = race condition"
`_tt`, `_killers`, `_history` as module globals meant two AIEngine
instances in a Tournament shared state. In practice this caused
test flakiness (puzzle_027) and potential tournament corruption.
- **Fix:** SearchContext per AIEngine instance.
- **Rule:** never store search state in module-level variables.
  Bundle into a context object owned by the caller.

### "Book moves must respect mandatory captures"
Opening book returned a quiet move when captures were mandatory.
The engine played an illegal move. This was a LEGAL CORRECTNESS bug,
not just a strength bug.
- **Rule:** before returning ANY move (book, bitbase, or search),
  verify it's legal in the current position. At minimum:
  `if board.has_any_capture(color)` → move must be a capture.

## Process traps

### "Backward-compat shims are load-bearing"
When we moved `controller.py` from `game/` to `app/`, we left a shim.
The shim is CRITICAL — old code, old settings files, external imports
all depend on it. Never delete a shim without verifying every importer.

### "Tests that always pass are worse than no tests"
Several tests were asserting trivially true things (`assert moves is
not None` on a position where None is impossible). These give false
confidence. Better: assert something SPECIFIC that would FAIL if the
code is wrong.

### "xfail tests are a strength benchmark"
We started with 7 xfailed tactical tests. After Texel tuning, 3 of
them started passing. xfails are NOT "broken tests we ignore" — they
are a quantitative measure of engine improvement. Never delete them;
promote them to passing when the engine grows strong enough.

## Time management

### "Parallel agents save wall-clock, not tokens"
3 agents running in parallel take the same total tokens as 3
sequential agents. But wall-clock drops from 30+30+30=90 min to
~35 min (longest agent). Worth it for the human waiting.

### "The QA agent pays for itself — but only with user-level testing"
The Opus QA audit found 12 bugs including 3 CRITICAL in one 2-hour
run. BUT the user then found 6 MORE bugs that QA missed — all in
the "non-default settings" category:
- Playing as Black (not White) → game doesn't start
- Hover dots wrong color when playing Black
- Theme not applied to child dialogs
- Window doesn't shrink after closing dock panel
- Inline styles overriding theme on specific buttons
- Board sizes different across windows

**Root cause:** QA only analyzed CODE, never "played as the user."
Code analysis catches logic bugs; user simulation catches UX bugs.
Both are required. The QA agent's checklist now includes mandatory
"play as user with non-default settings" steps.

### "Non-default settings are where bugs hide"
Developers test the default path. Users click "the other option."
Every setting with N values must be tested with ALL N values, not
just the default. If there's a Side selector with White/Black — test
Black. If there's a Theme with dark/light — test light. If there's
a panel that opens/closes — test the close path.

This is the single highest-ROI testing technique for UI apps.

### "Validation ranges must track schema changes"
GameSave validated `difficulty` in range 1-3, but the difficulty system
was expanded to 1-6. The validation was never updated. Result: every
save/autosave crashed, but autosave's `except Exception: pass` masked
the error. The user's game was never persisted — data loss on close.
- **Rule:** when expanding a value's range, grep for ALL validators.
- **Better rule:** define valid ranges as constants, not inline literals.
- **Detection:** test the save path with the DEFAULT settings, not just
  edge cases. The default difficulty (4) was outside the old range.

### "Drawn endgame detection must match actual draughts rules"
`_is_drawn_endgame` checked `bk >= 1 and wk >= 1` (any kings = draw).
But in Russian draughts, only 1K vs 1K is a theoretical draw. 2K vs 1K
and 3K vs 1K are wins. The engine treated winning endgames as draws.
- **Rule:** verify endgame detection against actual rules, not intuition.
- **Detection:** test with concrete positions (2K vs 1K, 3K vs 1K).

### "Never compare notations in different formats"
Game analyzer compared PDN numeric notation ("22-17") with algebraic
("c3-d4"). They never match. The fallback `delta_cp < 5.0` made every
move "best". Use position comparison instead of notation comparison
when the two sides might use different notation systems.
