# DECISIONS.md — Product & architectural decisions

Based on `RESEARCH.md`. Decisions are concrete and binding; each has
**Rationale**, **Trade-off**, and **Priority** (P0 = must ship,
P1 = should ship, P2 = nice-to-have).

The guiding star: **"the best Russian draughts application a serious
amateur or club player would open every day."** Not a chess-engine
research toy, not a casual mobile game. A tool.

---

## A. Format & interoperability

### D1 — PDN is the primary, default, and canonical save format
- **Decision:** Replace JSON save with **PDN 3.0** using
  `[GameType "25,W,8,8,A1,0"]` for Russian 8x8. JSON autosave keeps
  runtime state (TT, settings, cursor) but game history is written as
  PDN alongside.
- **Rationale:** PDN is the universal language of draughts software.
  Using JSON isolates us from every existing database, engine,
  puzzle set, and tool. Every competitor program in RESEARCH.md
  treats PDN as table-stakes.
- **Trade-off:** One-time migration cost; existing `*.json` saves
  must be readable for backward compat at least until v4.0.
- **Priority:** **P0**

### D2 — Drop JSON as a user-visible format
- **Decision:** `.json` game saves become deprecated. File dialog
  opens/saves `.pdn` only. Autosave stays internal JSON (state blob).
- **Rationale:** Two formats = confusion. Users should never see JSON.
- **Trade-off:** We must ship a one-time `json → pdn` converter.
- **Priority:** **P0** (ships with D1)

### D3 — FEN position support
- **Decision:** Implement FEN parse/emit for PDN `[SetUp "1"][FEN "..."]`
  tags. Required for position setup, puzzles, analysis from
  arbitrary positions.
- **Rationale:** Puzzles, studies, and analysis-from-position all
  depend on FEN. Without it, half the feature roadmap is blocked.
- **Trade-off:** Non-trivial parser (Russian-draughts notation quirks).
- **Priority:** **P0**

### D4 — Move notation: algebraic (`a3-b4`, `c3:e5`)
- **Decision:** Display and record moves in standard Russian-draughts
  algebraic notation: `-` for quiet moves, `:` or `x` for captures,
  colon is preferred (matches lidraughts/PDN convention).
- **Rationale:** Numeric notation (1-32) is International-draughts
  specific; algebraic is native to Russian draughts.
- **Trade-off:** Minor — our internal representation is already
  (y, x) coords; emitter is trivial.
- **Priority:** **P0**

---

## B. AI & engine architecture

### D5 — Engine and GUI communicate via a text protocol
- **Decision:** Refactor `AIEngine` behind a protocol boundary
  (`draughts/engine/protocol.py`). Protocol: line-based, stdin/stdout,
  inspired by UCI/DXP. Commands: `position <fen> moves ...`,
  `go depth N | movetime MS | infinite`, `stop`, `setoption name <K>
  value <V>`, `quit`. Responses: `info depth N score cp X nodes N pv
  ...`, `bestmove ...`.
- **Rationale:** Enables: headless tournaments, external-engine
  tournaments, multi-process analysis pane, CI regression tests,
  future neural engine swap-in. Matches Kingsrow/Scan/CheckerBoard
  model (DLL / DXP / UCI analogue). The hard part of this already
  exists (`headless.py`, `tournament.py`) — we are formalizing.
- **Trade-off:** Extra layer of indirection; today everything is
  in-process and direct function calls are slightly faster.
- **Priority:** **P0**

### D6 — Difficulty is expressed as approximate Elo, not as "уровень 1/2/3"
- **Decision:** Replace (Любитель/Нормал/Профессионал) with **6 levels
  mapped to approximate Elo strength**:
  - Level 1 ≈ 800 (depth 2, blunders on purpose 20% of time)
  - Level 2 ≈ 1100 (depth 3, blunders 10%)
  - Level 3 ≈ 1400 (depth 4)
  - Level 4 ≈ 1700 (depth 5 + quiescence)
  - Level 5 ≈ 2000 (depth 6 + quiescence + killer)
  - Level 6 ≈ max (depth 8+ + all features, iterative)
  Displayed as "Уровень 3 (~1400)". Old names kept as tooltips:
  "Уровень 2 — Любитель", etc.
- **Rationale:** Every modern draughts program does this. Elo is
  a universally understood currency. "Normal" means nothing across
  users.
- **Trade-off:** Our Elo calibration will be rough until we run
  a tournament gauntlet. Initial numbers are placeholders to
  be refined by self-play tournaments in M1.
- **Priority:** **P0**

### D7 — Add blundering behavior to low levels
- **Decision:** Levels 1–2 deliberately pick a non-best move with
  probability 20%/10%, picked from the top-K moves by eval. The
  blunder is proportional to eval gap (small eval gap = picked
  freely, big gap = rarely picked).
- **Rationale:** A depth-2 AI that plays 1400-Elo-perfectly is a
  terrible opponent for a beginner. Beginners need **winnable**
  games with realistic mistakes. Chess.com / Lichess bots do this.
- **Trade-off:** Non-deterministic, harder to test. Guard with a
  seed in dev builds.
- **Priority:** **P1**

### D8 — Opening book, built by self-play, shipped as a data file
- **Decision:** Implement an **opening book**: Zobrist-hash-keyed
  file storing `hash → list of (move, score, games)`. Generation
  pipeline: run a self-play tournament from the start position with
  engine at level 5, collect winning lines to depth 20, store.
  Target book size: <5 MB. Book lookup is O(1); book moves bypass
  search entirely at top levels.
- **Rationale:** Every top program has one; it is the #1 strength
  booster before endgame DBs. Russian-draughts openings (Жертва
  Филипповского, Кол, Городская, etc.) are well known and
  unambiguous — easy to codify.
- **Trade-off:** Generation pipeline is slow (hours). Need tests to
  guarantee determinism of the book itself.
- **Priority:** **P1**

### D9 — Endgame bitbase (4-piece WLD) for Russian draughts
- **Decision:** Build a **4-piece WLD bitbase** (all positions with
  ≤4 pieces, one of which is a king) by retrograde analysis. Store
  as a packed file (<20 MB). Engine probes the bitbase at leaf
  nodes when `piece_count <= 4`. Defer 5-piece and 6-piece to a
  future milestone.
- **Rationale:** King-vs-king endings and 2v1 endings are the
  biggest source of our horizon bugs (the whole reason
  `quiescence fail-soft` patch was needed). A WLD bitbase trivially
  solves them. 4-piece space is ~10^6 positions — tractable on a
  laptop overnight.
- **Trade-off:** Retrograde analysis code is non-trivial. Adds a
  binary artifact to the distribution.
- **Priority:** **P1**

### D10 — Drop "adaptive depth" heuristic, replace with time-based search
- **Decision:** The current rule "if >16 pieces, cap depth at 4; if
  <6, +2" is ad-hoc. Replace with **time-control search**:
  the engine is given N milliseconds per move (derived from the
  difficulty level), runs iterative deepening, and returns the
  best move found within the budget.
- **Rationale:** Time controls are how every real draughts
  program plays. Depth-capped search feels jerky — instant at the
  start, slow in the middlegame, fast again in the endgame.
  Time-limited feels natural and uses hardware optimally.
- **Trade-off:** Requires cooperative search interruption; we
  already have that (`stop_requested` flag).
- **Priority:** **P0**

### D11 — Drop "golden corner" / ad-hoc Russian-draughts eval tricks
- **Decision:** Audit the evaluation function and delete heuristics
  that cannot be justified by measurement (golden corners, distance
  to opponent king, etc.). Replace with a **self-play-trained
  linear eval** on simple features (material, advancement, king
  count, mobility, tempo). Tuned by `draughts/engine/tuner.py` via
  Texel's method.
- **Rationale:** Hand-tuned magic numbers are untestable technical
  debt. Scan proved that automatic tuning beats hand-tuning for
  this exact task.
- **Trade-off:** Requires building a tuner; short-term, the eval
  may get WEAKER before it gets stronger. We must measure via a
  tournament against the current baseline.
- **Priority:** **P1**

---

## C. User-facing features

### D12 — Analysis mode is a P0 feature
- **Decision:** Add an **Analysis window** with:
  - Live engine pane (eval in cp, PV line, depth, nps).
  - Full-game analysis button ("проанализировать партию") — walks
    every move, produces annotations (`!!`, `!`, `!?`, `?!`, `?`,
    `??`) by eval delta thresholds.
  - Move list with annotations inline.
  - Click on any move → engine evaluates from that position.
  - Eval curve plot (small chart under the move list).
- **Rationale:** This is the single most-used feature in every
  draughts program. Without it we are not competitive.
- **Trade-off:** Significant UI work (maybe 30% of M3).
- **Priority:** **P0 for M3**

### D13 — Puzzle / tactics trainer
- **Decision:** Add a **Puzzles mode**: load a bundled set of
  hand-curated and mined tactical positions (capture combinations,
  forced wins), user finds the best move, engine verifies, streak
  counter, elementary rating. Puzzles stored as PDN with
  `[SetUp "1"][FEN ...]` plus a solution tag.
- **Rationale:** Lidraughts puzzles are the most-played feature on
  their site. Turns single-session curiosity into repeated use.
  Mining our tournament games for blunders provides free puzzle
  material.
- **Trade-off:** Curation is effort; initial puzzle set (~100) must
  be hand-verified.
- **Priority:** **P1 (M4)**

### D14 — Board editor / position setup
- **Decision:** Add a **position editor** accessible from menu:
  place/remove pieces, set side-to-move, export FEN, play from that
  position vs engine or analyze. Keyboard: `E` enters editor, `Esc`
  exits.
- **Rationale:** Prerequisite for puzzles, for studying endings,
  and for debugging engine bugs. Cheap to build on top of
  existing `board_widget.py`.
- **Trade-off:** None meaningful.
- **Priority:** **P0 for M3**

### D15 — Options dialog redesign
- **Decision:** Redesign `dialogs.py::OptionsDialog` with tabs:
  1. **Игра:** side (white/black), Elo level, time per move, hints
     for mandatory captures.
  2. **Движок:** transposition-table size, threads, opening book
     on/off, endgame bitbase on/off, max depth override (for debug).
  3. **Интерфейс:** board theme (classic/dark wood), piece style
     (flat/3D), move animations on/off, coordinates on/off,
     highlight last move, show legal moves on hover.
  4. **Анализ:** annotation thresholds (cp deltas for `?`, `??`),
     eval display format (cp vs win%), auto-analyze on load.
- **Rationale:** Current options dialog is a flat list of 5 items.
  We need depth once difficulty is Elo-calibrated and the engine is
  configurable.
- **Trade-off:** A lot of widgets. But each is backed by a setting
  we already want.
- **Priority:** **P0 for M2**

### D16 — "Hint" button that actually explains
- **Decision:** `Ctrl+H` asks the engine for the best move at the
  user's current level and **highlights it on the board plus
  shows a one-line reason** ("bishops a1-h8 dominated") from PV.
- **Rationale:** Low-friction learning. Better than undo.
- **Priority:** **P2**

### D17 — Undo/redo unlimited at all levels (currently amateur-only)
- **Decision:** Remove the level-1-only undo limitation. Undo/redo
  are standard in every draughts program. The "serious players
  shouldn't undo" argument is gatekeeping, not design.
- **Rationale:** Analysis mode implicitly allows rewinding anyway.
  Preventing undo at high levels just annoys users.
- **Priority:** **P0 for M2**

### D18 — Dark mode + light mode board themes
- **Decision:** Current "dark wood" is the default; add a **light
  classic** theme (cream + brown) for daytime use. Theme selectable
  in options (D15).
- **Priority:** **P2**

### D19 — Clock / time control display
- **Decision:** Add an optional clock display for both players
  when time-controlled games are enabled (follows D10). Off by
  default; toggleable.
- **Priority:** **P2**

---

## D. What to DROP or REFRAME

### D20 — Drop: three hard-coded difficulty names
- **Why:** Replaced by Elo ladder (D6). Legacy names preserved only
  as tooltips.

### D21 — Drop: the "messages.txt" AI commentary feature
- **Decision:** Remove the random AI chatter lines during thinking.
  No serious program has this.
- **Rationale:** Cute but out of place. Detracts from "serious tool"
  positioning.
- **Trade-off:** Tiny loss of charm; can be revived as an easter-egg
  setting if users complain.
- **Priority:** **P1**

### D22 — Drop: the fixed "white at the bottom, black at top, play as
  white by default" assumption when not playing as white
- **Decision:** Board orientation follows the player automatically.
  `--black` flag stays but is redundant; `invert_color` setting stays
  exactly as it does today.
- **Priority:** Already half-implemented; verify in M2.

### D23 — Drop: `--depth N` as a user-visible CLI flag
- **Decision:** `--depth` becomes a dev flag (moved to `dev.py`);
  users set difficulty/time. Reduces confusion: there is one knob
  for strength.
- **Priority:** **P1**

### D24 — Re-scope: `resources/messages.txt` and "fun" strings
- Merge with D21. Anything not strictly required stays off by
  default.

---

## E. Module structure (team-readiness)

### D25 — Split the `draughts/game/` package
- **Decision:** Reorganize into:
  ```
  draughts/
      core/              # pure game logic, no Qt, no I/O
          board.py       # NumPy board, moves, rules
          move.py        # Move dataclass, notation helpers
          rules.py       # mandatory capture, promotion, draws
          zobrist.py     # (new) hashing
      engine/            # the AI, pluggable
          protocol.py    # text protocol
          search.py      # alpha-beta, LMR, quiescence, killers
          tt.py          # transposition table
          eval.py        # evaluation function
          book.py        # opening book
          bitbase.py     # endgame bitbase
          tuner.py       # Texel-method tuner
      io/                # PDN, FEN, autosave, JSON legacy
          pdn.py
          fen.py
          save.py
      ui/                # PyQt6, unchanged structure
      tools/             # headless, tournament, benchmark, analyze
          headless.py
          tournament.py
          analyze.py
  main.py                # thin CLI wrapper
  ```
- **Rationale:** `ai.py` is 1141 lines, `controller.py` is 492. A
  second developer cannot safely change either. Splitting along
  the layers above mirrors how Scan and Kingsrow are structured
  and makes each module testable in isolation.
- **Trade-off:** One big PR that touches every import. Schedule it
  FIRST in M1 so everything downstream lands in the new layout.
- **Priority:** **P0, first task of M1**

### D26 — `draughts/engine/` has no Qt imports, ever
- **Decision:** Enforce via a ruff lint rule and a test that imports
  `draughts.engine` in a subprocess with `PYTHONPATH` stripped of
  PyQt6 and asserts success.
- **Rationale:** Enables headless CI and future engine-as-CLI
  distribution without Qt dependency.
- **Priority:** **P0**

### D27 — Add type checking in CI (mypy strict on core + engine)
- **Decision:** `mypy --strict draughts/core draughts/engine` runs
  in `pytest` pre-commit.
- **Rationale:** NumPy code is easy to get wrong; types catch it.
- **Priority:** **P1**

### D28 — Version bump plan
- **Decision:** M1 lands as 3.3.0 (refactor + engine protocol).
  M2 lands as 3.4.0 (PDN, difficulty, options). M3 lands as 4.0.0
  (analysis, editor, book) — breaking enough to warrant major bump
  because save-format default changes and CLI flags change.
- **Priority:** informational.

---

## F. Ecosystem & interoperability (M5)

### D29 — DXP protocol support for engine interoperability
- **Decision:** Implement the **Draughts eXchange Protocol (DXP)** —
  the de facto standard for engine-to-engine communication in draughts.
  Support both server mode (our engine listens, external GUI connects)
  and client mode (we connect to an external engine). DXP is simpler
  than UCI/CECP: 7 message types (CHAT, MOVE, GAMEREQ, GAMERESP,
  MOVEACK, GAMEEND, BACKREQ). Implementation lives in
  `draughts/engine/dxp.py`, exposed as `python -m draughts.engine --dxp`.
- **Rationale:** DXP is how Scan communicates with GUIs. CheckerBoard
  uses it for engine plugins. FMJD computer championships use DXP
  for automated play. Without DXP, our engine is an island — it cannot
  participate in the ecosystem. This is the single most impactful
  interoperability feature. It also enables A/B benchmarking against
  external engines (not just self-play), which directly improves our
  ability to measure strength.
- **Trade-off:** Networking code (TCP sockets) in the engine package.
  Must be careful not to violate D26 (no Qt in engine). DXP was
  designed for 10x10 International; we need the Russian-draughts
  adaptation (same protocol, different GameType and board encoding).
- **Priority:** **P0 (M5)**

### D30 — FEN clipboard integration
- **Decision:** Add **copy/paste FEN** to/from system clipboard.
  `Ctrl+C` in editor mode (or "Копировать FEN" menu) copies the
  current position as FEN. `Ctrl+V` (or "Вставить позицию" menu)
  reads FEN from clipboard and loads it. Auto-detect FEN format
  (standard Russian-draughts notation: `W:Wa1,b2,...:Bc7,d8,...`).
- **Rationale:** This is the fastest way to share positions between
  programs. Lidraughts, CheckerBoard, and Aurora all support FEN
  copy/paste. Without it, users must save/load files just to move
  a position between our app and a website. The FEN infrastructure
  already exists (`fen.py`); this is pure UI wiring.
- **Trade-off:** None meaningful. Clipboard access is trivial in Qt.
- **Priority:** **P0 (M5)**

### D31 — Variation tree (branching game tree)
- **Decision:** Replace the current linear move list with a **tree
  data structure** that supports branching. When the user goes back to
  move N and plays a different move, a new branch is created (the
  original line preserved). The tree widget shows mainline + variations
  with expand/collapse. PDN export uses RAV (Recursive Annotation
  Variation) syntax: `1. a3-b4 {main} (1. c3-d4 {alt}) 1... f6-e5`.
  Analysis annotations are attached to tree nodes, not a flat list.
- **Rationale:** Every serious draughts/chess program has a variation
  tree. It is the foundation of analysis workflow: "what if I played
  this instead?" Without it, our analysis mode is look-only, not
  exploratory. Dam 3.0 and CheckerBoard set the standard. Lidraughts
  Studies are built on variation trees.
- **Trade-off:** This is the most complex single feature in M5. It
  requires: a tree data structure for game state, a tree view widget,
  RAV support in PDN parser/emitter, and reworking how the controller
  tracks game position. Estimated XL effort.
- **Priority:** **P0 (M5)**

### D32 — PDN database browser
- **Decision:** Add a **database view** for multi-game PDN files.
  List view with sortable columns (White, Black, Event, Date, Result).
  Filter by text (player name, event). Position search: given the
  current board, find all games in the database that transited through
  this position. Double-click loads a game into the main window.
- **Rationale:** Aurora Borealis and CheckerBoard define what serious
  users expect: a personal game collection they can search, filter,
  and study. Our PDN parser already handles multi-game files. This is
  the "database-first workflow" that separates a study tool from a
  play-only app.
- **Trade-off:** Position search requires hashing each game's positions
  at load time — memory cost proportional to database size. For a
  1000-game file this is manageable; for 100K+ games we'd need an
  indexed database (SQLite). Start with in-memory for v1.
- **Priority:** **P1 (M5)**

### D33 — 5-piece endgame bitbase
- **Decision:** Extend retrograde analysis from 3-piece to **5-piece
  WLD**. This puts us on par with programs like Scan (which has 6-piece)
  and far ahead of most Russian-draughts-specific software. Use a
  **binary format** (not JSON) to keep file size manageable. Expected:
  100M+ entries, ≤500 MB. Generation may take days; ship as a
  downloadable data pack if too large to bundle.
- **Rationale:** 4-piece is table stakes; 5-piece is where perfect
  endgame play begins to matter in practical games. The difference
  between 3-piece and 5-piece is the difference between "avoids
  obvious blunders in trivial endings" and "plays complex endings
  perfectly." This directly impacts perceived strength at the highest
  difficulty levels.
- **Trade-off:** Generation time (days), disk size, binary format
  complexity. May need a separate download/install step.
- **Priority:** **P1 (M5)**

### D34 — Opening book format compatibility
- **Decision:** Research and implement **readers for external draughts
  opening book formats**. At minimum: ability to import positions from
  plain-text or PDN-based book files used by other programs. Merge
  imported positions into our Zobrist-keyed format. This is about
  bootstrapping book quality from the ecosystem, not building
  everything from scratch.
- **Rationale:** Self-play book generation is slow and limited by
  our engine's strength. The Russian draughts community has published
  opening theory books. Being able to import them is a force multiplier.
- **Trade-off:** Format research required; reverse-engineering closed
  binary formats may not be feasible. Focus on open/text formats first.
- **Priority:** **P2 (M5)**

### D35 — Internationalization (i18n) infrastructure
- **Decision:** Extract all user-visible strings into **gettext `.po`
  files**. Wrap all UI strings in `_()`. Ship with Russian (primary)
  and English. This does not mean translating everything now — it means
  making translation *possible* without code changes.
- **Rationale:** The app is Russian-only. Adding English would roughly
  double the potential audience. More importantly, the i18n
  infrastructure prevents hardcoded strings from accumulating further.
  Every new feature added without i18n makes the eventual migration
  harder.
- **Trade-off:** Moderate effort to wrap all existing strings. Minor
  impact on code readability. But the earlier we do it, the less
  painful it is.
- **Priority:** **P2 (M5)**

---

## G. Priority summary

| # | Decision | Priority |
|---|---|---|
| D1 | PDN default format | **P0** |
| D2 | Drop JSON user-visible | **P0** |
| D3 | FEN support | **P0** |
| D4 | Algebraic notation | **P0** |
| D5 | Engine protocol | **P0** |
| D6 | Elo-based difficulty | **P0** |
| D7 | Blundering low levels | P1 |
| D8 | Opening book | P1 |
| D9 | 4-piece endgame bitbase | P1 |
| D10 | Time-based search | **P0** |
| D11 | Auto-tuned eval | P1 |
| D12 | Analysis mode | **P0 (M3)** |
| D13 | Puzzle trainer | P1 (M4) |
| D14 | Board editor | **P0 (M3)** |
| D15 | Tabbed options dialog | **P0 (M2)** |
| D16 | Hint button | P2 |
| D17 | Unlimited undo | **P0 (M2)** |
| D18 | Light theme | P2 |
| D19 | Clock display | P2 |
| D20 | Drop hardcoded difficulty names | **P0** |
| D21 | Drop messages.txt chatter | P1 |
| D22 | Board orientation follows player | verify |
| D23 | `--depth` dev-only | P1 |
| D25 | Module split | **P0 (M1)** |
| D26 | Engine has no Qt | **P0 (M1)** |
| D27 | mypy strict in CI | P1 |
| D28 | Version bump plan | informational |
| D29 | DXP protocol support | **P0 (M5)** |
| D30 | FEN clipboard integration | **P0 (M5)** |
| D31 | Variation tree (game tree) | **P0 (M5)** |
| D32 | PDN database browser | P1 (M5) |
| D33 | 5-piece endgame bitbase | P1 (M5) |
| D34 | Opening book format compat | P2 (M5) |
| D35 | i18n infrastructure | P2 (M5) |
