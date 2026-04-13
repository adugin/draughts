# ROADMAP.md — Ordered feature roadmap

Milestones are **strictly sequential for load-bearing work**. Within a
milestone, features can be parallelized. Complexity codes:
**S** = half day, **M** = 1-2 days, **L** = 3-5 days, **XL** = 1-2 weeks.
All estimates assume a single developer.

Each feature references the driving decision (`Dxx`) in `DECISIONS.md`.

---

## M1 — Foundation (refactor, protocol, engine plumbing) --- COMPLETE

**Goal:** make the codebase safe to extend; no user-visible changes.
**Status:** COMPLETE (2026-04-11). See `M1_REPORT.md`.

| # | Feature | Decision | Status |
|---|---------|----------|--------|
| 1 | Module split (ai/ package, app/, engine/, tools/) | D25, D26 | DONE |
| 2 | Engine text protocol (`python -m draughts.engine`) | D5 | DONE |
| 3 | Time-controlled search (`find_move_timed`) | D10 | DONE |
| 4 | Baseline Elo calibration tournament | D6 | PARTIAL -- placeholder numbers, 6 games/pair only |
| 5 | Evaluation audit + regression harness (72 tactical tests) | D11 | DONE |
| 6 | TT size & threads options | — | PARTIAL -- UI exists, backend stub |

---

## M2 — Standards compliance (PDN, notation, options, undo) --- COMPLETE

**Goal:** bring file formats, notation, and options UX to industry standard.
**Status:** COMPLETE (2026-04-11). Landed inside M1 session.

| # | Feature | Decision | Status |
|---|---------|----------|--------|
| 7 | PDN 3.0 write/read + GameType 25 + FEN | D1-D4 | DONE |
| 8 | Legacy JSON to PDN converter | D2 | PARTIAL -- function exists, auto-trigger missing |
| 9 | Elo-based difficulty in UI (6 levels) | D6 | DONE |
| 10 | Unlimited undo/redo at all levels | D17 | DONE |
| 11 | Tabbed options dialog (4 tabs) | D15 | DONE |
| 12 | Drop AI chatter / messages.txt | D21 | DONE |
| 13 | CLI simplification (--depth to dev only) | D23 | DONE |

---

## M3 — Professional features (analysis, book, bitbase, editor) --- COMPLETE

**Goal:** add the features professional users actually want.
**Status:** COMPLETE (2026-04-12). All major features shipped.

| # | Feature | Decision | Status |
|---|---------|----------|--------|
| 14 | Position / board editor | D14 | DONE |
| 15 | Live engine analysis pane (F3 toggle) | D12 | DONE |
| 16 | Full-game analysis with annotations | D12 | DONE |
| 17 | Eval curve plot (click-to-navigate) | D12 | DONE |
| 18 | Opening book (self-play generated) | D8 | DONE -- 1,572 positions (below 2,000 target) |
| 19 | Endgame bitbase | D9 | DONE -- 3-piece WLD (target was 4-piece), 399K entries |
| 20 | Evaluation auto-tuning (Texel method) | D11 | DONE |

---

## M4 — Training & polish --- COMPLETE

**Goal:** features that make users return daily.
**Status:** COMPLETE (2026-04-12). All features shipped.

| # | Feature | Decision | Status |
|---|---------|----------|--------|
| 21 | Puzzle trainer (solve/hint/streak) | D13 | DONE -- 30 puzzles (below 100 target) |
| 22 | Puzzle auto-mining from analyzed games | — | DONE |
| 23 | Hint button (Ctrl+H) | D16 | PARTIAL -- shows eval score, no PV line/reason |
| 24 | Board themes (7 TOML themes + theme engine) | D18 | DONE (exceeded) |
| 25 | Clock display (cumulative per side) | D19 | DONE |
| 26 | Last-move highlight + legal-move hover dots | — | DONE |

**Bonus shipped:** deliberate blundering L1-L2 (D7), board flip for black
(D22), mypy strict (D27), 5 agents + 6 playbooks, benchmark infra, QA
bug fixes (BUG-004 through BUG-008).

---

## M5 — Ecosystem & Depth

**Goal:** Transform DRAUGHTS from a capable standalone app into a program
that participates in the draughts software ecosystem. Deepen existing
features to meet world-class acceptance criteria. Enable interoperability
with external engines, databases, and tools.

**Target version:** 4.0.0 (major bump — DXP protocol, variation trees,
and database browsing are architectural changes).

**Estimated effort:** ~6-8 weeks (1 dev).

### Phase A: Finish what's started (fix partial items from M1-M4)

#### 27. Expand endgame bitbase to 4-piece WLD (D9 completion)
- **Desc:** Extend retrograde generator to cover all positions with
  exactly 4 pieces. This is the original D9 target. Update search to
  probe at `piece_count <= 4`. Expected: ~5-15M entries, ~50-150 MB.
- **Complexity:** L
- **Depends on:** —
- **RICE:** R=all users, I=high (eliminates horizon bugs in 2v2),
  C=high (generator exists), E=L. **Score: 9**
- **Acceptance:**
  - Bitbase covers all 4-piece positions (pawns + kings).
  - Engine never loses a won 2v2 king ending (20-position regression).
  - File ≤ 200 MB.
  - Generation completes overnight on a laptop.

#### 28. Expand opening book to 5,000+ positions (D8 completion)
- **Desc:** Run deeper self-play tree exploration (depth 25+, higher
  time control). Target: 5,000+ unique positions covering all major
  Russian draughts openings (Жертва Кукуева, Кол, Городская, Косяк,
  Отыгрыш, Обратная, Старая). Add known theory lines from published
  sources.
- **Complexity:** M (generation time is the bottleneck, code is trivial)
- **Depends on:** —
- **RICE:** R=all, I=medium (opening play variety), C=high, E=M. **Score: 7**
- **Acceptance:**
  - Book ≥ 5,000 positions.
  - Engine with book scores ≥ 55% vs same engine without over 100 games.
  - File ≤ 5 MB.

#### 29. Expand puzzle database to 100+ curated puzzles (D13 completion)
- **Desc:** Mine puzzles from deeper self-play games (depth 7+, longer
  time controls). Hand-verify quality. Add classical composition
  positions (etudes). Target: 100+ puzzles across difficulty 1-4.
- **Complexity:** M
- **Depends on:** —
- **RICE:** R=all, I=high (retention driver), C=high, E=M. **Score: 8**
- **Acceptance:**
  - 100+ puzzles ship with the app.
  - Distribution: ~30% difficulty 1-2, ~40% difficulty 3, ~30% difficulty 4.
  - All solutions verified by engine at depth 8.

#### 30. Complete Elo calibration with proper tournament (D6 completion)
- **Desc:** Run 100+ game per-pair self-play tournament using time-based
  search as the primary strength dial. Produce authoritative Elo numbers
  for levels 1-6. Update `elo.py` with measured values. Verify monotonicity.
- **Complexity:** S (mostly compute time)
- **Depends on:** —
- **RICE:** R=all, I=medium, C=high, E=S. **Score: 7**

#### 31. Wire JSON-to-PDN auto-conversion on first launch (D2 completion)
- **Desc:** On startup, if legacy `autosave.json` or `*.json` game files
  exist in the save directory, auto-convert to `.pdn` using existing
  `json_to_pdn()`. Show a one-time notification. Keep both files.
- **Complexity:** S
- **Depends on:** —
- **RICE:** R=existing users only, I=low, C=high, E=S. **Score: 4**

#### 32. Hint button: show PV line and textual reason (D16 completion)
- **Desc:** Enhance `get_hint()` to run at depth 6 (not 4), extract the
  full PV line, and display it in a tooltip or status area. Format:
  "c3-d4 (PV: c3-d4 f6-e5 d4:f6 g7:e5) оценка: +1.5".
- **Complexity:** S
- **Depends on:** —
- **RICE:** R=beginners, I=medium, C=high, E=S. **Score: 6**

### Phase B: Ecosystem interoperability (new capabilities)

#### 33. DXP protocol support (D29)
- **Desc:** Implement the Draughts eXchange Protocol (DXP) — the
  standard for engine-to-engine communication in draughts. Both
  server and client modes. This enables:
  - Playing our engine against Scan, Kingsrow (via adapter), etc.
  - Participating in automated tournaments (FMJD computer championships).
  - External GUIs (CheckerBoard, Dam) hosting our engine.
- **Complexity:** L
- **Depends on:** item 2 (engine protocol — done)
- **RICE:** R=developers+advanced, I=very high (ecosystem unlock),
  C=medium, E=L. **Score: 8**
- **Acceptance:**
  - `python -m draughts.engine --dxp --port 27531` starts a DXP server.
  - Successfully plays a 10-game match against itself via DXP.
  - PDN of games recorded automatically.

#### 34. FEN clipboard integration (D30)
- **Desc:** `Ctrl+C` in editor mode copies FEN to system clipboard.
  `Ctrl+V` in editor mode or main window pastes a FEN and loads the
  position. Detect FEN in clipboard on "Вставить позицию" menu action.
- **Complexity:** S
- **Depends on:** item 14 (editor — done)
- **RICE:** R=club+advanced, I=high (workflow), C=high, E=S. **Score: 8**
- **Acceptance:**
  - Round-trip: copy FEN from lidraughts → paste into DRAUGHTS → position matches.
  - Works with standard Russian-draughts FEN notation.

#### 35. Variation tree (game tree with branching) (D31)
- **Desc:** Replace linear move list with a tree structure. User can:
  branch off at any move, explore alternatives, navigate the tree.
  Store as PDN with RAV (Recursive Annotation Variation). Tree view
  widget with expand/collapse, current-move highlight, annotations.
- **Complexity:** XL
- **Depends on:** item 7 (PDN — done), item 16 (analysis — done)
- **RICE:** R=club+advanced, I=very high (analysis workflow),
  C=medium (complex), E=XL. **Score: 7**
- **Acceptance:**
  - User plays 10 moves, goes back to move 5, plays alternative — both
    lines visible in tree.
  - PDN export includes RAV variations.
  - Tree navigation with keyboard arrows.
  - Analysis annotations attached to correct tree nodes.

#### 36. PDN database browser (D32)
- **Desc:** Load a multi-game PDN file (hundreds/thousands of games).
  List view with columns: White, Black, Event, Date, Result. Filter
  by player name, result, opening position. Click to load game. Search
  by current board position (find all games that reached this position).
- **Complexity:** L
- **Depends on:** item 7 (PDN — done)
- **RICE:** R=club+advanced, I=high (study workflow), C=medium, E=L.
  **Score: 7**
- **Acceptance:**
  - Loads a 1000-game PDN file in < 3 seconds.
  - Position search finds all matching games.
  - Double-click opens game in main window.

### Phase C: Strength & polish

#### 37. 5-piece endgame bitbase (D33)
- **Desc:** Extend retrograde analysis to 5 pieces. This is where
  serious programs separate from amateur ones. Expected: 100M+ entries.
  May require binary format (not JSON) for size.
- **Complexity:** XL
- **Depends on:** item 27 (4-piece done)
- **RICE:** R=advanced, I=very high (perfect endgame), C=medium
  (scale issues), E=XL. **Score: 6**
- **Acceptance:**
  - 5-piece bitbase generates (may take days).
  - Binary format, ≤ 500 MB.
  - Engine plays 5-piece endings perfectly.

#### 38. TT resize backend + configurable hash size (D6, D15 completion)
- **Desc:** Wire the "Хеш-таблица" option in OptionsDialog to actually
  resize the transposition table. Implement MB-based sizing.
- **Complexity:** S
- **Depends on:** —
- **RICE:** R=advanced, I=medium, C=high, E=S. **Score: 5**

#### 39. Opening book format compatibility (read Kingsrow/Scan books) (D34)
- **Desc:** Research and implement readers for common draughts opening
  book formats. At minimum, support importing positions from external
  book files and merging into our JSON format.
- **Complexity:** M
- **Depends on:** item 28 (book expansion)
- **RICE:** R=advanced, I=medium, C=low (format research needed), E=M.
  **Score: 4**

#### 40. Multi-language support (i18n infrastructure) (D35)
- **Desc:** Extract all user-visible strings into gettext `.po` files.
  Ship with Russian (primary) and English. All UI strings go through
  `_()` wrapper. This is infrastructure for future localization.
- **Complexity:** M
- **Depends on:** —
- **RICE:** R=international users, I=medium, C=high, E=M. **Score: 5**

---

## M6+ — Future (deferred, not committed)

- **Multiplayer** — LAN first (protocol already lends itself), then
  online (would likely reuse lidraughts-style DXP gateway).
- **Neural evaluation** — once tuning (#20) plateaus; train a small
  MLP on self-play games a la Kingsrow's 2022 rebuild.
- **SMP multi-threading** — the `Threads` option stub becomes real.
  Lazy SMP is the simplest path.
- **6-piece endgame bitbase** — extend after 5-piece ships.
- **Studies / annotated game editor** — full variation tree with
  user comments, a la lidraughts studies (partially unlocked by #35).
- **Mobile / web port** — not until the desktop product is complete.
- **Variant support (International 10x10, Brazilian, etc.)** —
  explicitly excluded; revisit only after M5 ships.
- **Hub protocol** (CheckerBoard native) — consider after DXP proves out.
- **Endgame tablebase format compatibility** (Kingsrow .egdb, Scan format)
  — research track for when 5-piece bitbase is done.

---

## M5 Critical path

```
Phase A (parallel — all independent):
  #27 4-piece bitbase
  #28 5000+ book         ─┐
  #29 100+ puzzles        │
  #30 Elo calibration     │  All can start immediately
  #31 JSON auto-convert   │
  #32 Hint PV display    ─┘

Phase B (partial dependencies):
  #33 DXP protocol              (independent)
  #34 FEN clipboard             (independent)
  #35 Variation tree            (independent, but XL)
  #36 PDN database browser      (independent)

Phase C (sequential):
  #37 5-piece bitbase           (after #27)
  #38 TT resize                 (independent)
  #39 Book format compat        (after #28)
  #40 i18n infrastructure       (independent)
```

Phase A items are small/medium fixes that complete M1-M4 promises.
Phase B items are the ecosystem-defining new capabilities.
Phase C items are stretch goals that deepen strength.

---

## Estimated effort

| Phase | Weeks (1 dev) | Cumulative |
|-------|---------------|------------|
| M1-M4 (done) | ~3 (actual!) | 3 |
| M5 Phase A (fix partial) | 1.5 | 4.5 |
| M5 Phase B (ecosystem) | 4 | 8.5 |
| M5 Phase C (strength) | 2.5 | 11 |
| **Total to M5 complete** | **~8** | |
