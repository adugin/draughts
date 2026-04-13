# Guide: Agent Orchestration Patterns

**When to use:** When planning multi-agent work sessions. This guide
captures patterns that worked well and anti-patterns that wasted tokens.

## Model selection

| Task type | Model | Why |
|---|---|---|
| Strategic decisions, architecture, root-cause analysis | **Opus** | Needs deep reasoning, trade-off evaluation |
| Mechanical refactoring, data collection, test writing | **Sonnet** | Clear instructions, predictable output |
| Simple lookups, formatting | **Haiku** | Not used in this project (insufficient for code) |

**Rule of thumb:** if you can describe the task in 3 sentences with
clear acceptance criteria → Sonnet. If it requires judgment calls or
understanding WHY → Opus.

**Cost reality from this project:** Opus 74% / Sonnet 25% of total
tokens. Cache hit rate 97%. The Opus overhead was justified — every
Opus task produced strategic value (PO decisions, QA bug finds,
test audit insights).

## Parallel vs sequential

### Parallel (spawn in ONE message with multiple Agent calls)
Use when tasks touch DIFFERENT files:
- Module moves (controller → app/) + ai.py split → no conflicts
- PDN writer + board editor + opening book → different packages
- Puzzle trainer + UX polish + blundering → different features

### Sequential (wait for one to finish before spawning next)
Use when tasks touch the SAME files or have data dependencies:
- SearchContext extraction → THEN ai.py split (depends on ctx)
- PO analysis → THEN implementation (depends on decisions)
- Bug fix → THEN test that verifies the fix

### Wave pattern (what worked best)
```
Wave 1: Research (PO + Module Audit + DB Collector) — 3 parallel
Wave 2: Foundation refactoring — 2 parallel (different file sets)
Wave 3: Feature implementation — 3 parallel (PDN + headless + tactics)
Wave 4: More features — 2 parallel (AI changes + UI changes)
Wave 5+: Continue in waves of 2-3 parallel agents
Final: QA audit (single Opus agent, comprehensive)
```

## Prompt structure for sub-agents

### What makes a GOOD agent prompt:
1. **Context block** — project path, branch, what to read first
2. **Mission** — specific deliverables, not vague goals
3. **Constraints** — what NOT to touch, time budget, model limits
4. **Validation** — exact commands to run (pytest, ruff, head2head)
5. **Commit instructions** — message format, when to push
6. **Budget** — wall-clock minutes, prevents runaway agents

### What makes a BAD agent prompt:
- "Fix the code" (no acceptance criteria)
- "Make it better" (no measurement)
- "Do whatever you think is best" (no constraints → chaos)
- Prompt > 2000 words (agent loses focus on the important parts)

### Template that worked:
```
You are doing X for the DRAUGHTS project.

## Context
- Project: path, branch
- Read: specific files for context

## Mission
### Task A — <name>
<what to do, acceptance criteria>

### Task B — <name>
<what to do, acceptance criteria>

## Validation (mandatory)
1. pytest → all green
2. ruff → clean
3. specific smoke test

## Commits
N commits, one per task, descriptive messages.

## Budget
N minutes.

Start by reading <file>.
```

## Anti-patterns learned

### 1. "Improve everything" agents
❌ Spawned agent to "improve AI and find weaknesses" without specific
   acceptance criteria. Agent ran for 2 hours, produced a report,
   but the report wasn't actionable.
✅ Better: "Run 10 games at depth 5, measure blunder rate, compare
   with baseline, report specific positions where AI blundered."

### 2. Agents modifying the same file
❌ Two agents both editing `main_window.py` → merge conflicts, one
   agent's work overwritten.
✅ Better: sequence them, or split the file first.

### 3. Agent not clearing state
❌ Agent ran head2head but forgot `ai._default_ctx.clear()` between
   games → TT pollution → wrong results.
✅ Better: include state-clearing in the validation instructions.

### 4. Trusting agent's self-reported numbers
❌ Agent said "improvement confirmed" but used only 20 games (CI too
   wide). Actual improvement was noise.
✅ Better: require 60+ games or SPRT with explicit H0/H1.

## Orchestrator responsibilities

The orchestrator (main chat, Opus) should:
1. **Plan waves** — which agents can run in parallel
2. **Write precise prompts** — not delegate prompt-writing
3. **Verify results** — run pytest yourself after agent completes
4. **Track state** — use TodoWrite to know what's done/pending
5. **Push commits** — batch-push after verifying, not let agents push
   without review (though in practice we let agents push for speed)
6. **Stay lean** — don't read agent output files (they're huge JSONL).
   Read only the summary in the task notification.
