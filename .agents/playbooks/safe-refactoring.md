# Checklist: Safe Module Refactoring

**When to use:** Before splitting a large file, moving modules between
packages, or reorganizing the import graph.

## Why this exists

We split `ai.py` (1141 lines) into 6 sub-modules, moved `controller.py`
to `app/`, moved `renderer.py` to `tools/`, extracted `analysis.py`
from `headless.py`. Each step was atomic and verified. Zero behavior
regressions because we followed this sequence.

## The sequence (order matters)

### Phase 0: Preparation
- [ ] Run `pytest` — green baseline
- [ ] Run `perf_baseline.py` — record numbers
- [ ] Commit any uncommitted work
- [ ] `cp target_file.py .planning/ai_old.py` — backup for head2head

### Phase 1: Extract shared state FIRST
Before splitting a file that has module-level mutable state:
- [ ] Identify ALL globals (`_tt`, `_killers`, `_history`, etc.)
- [ ] Bundle into a dataclass (`SearchContext`)
- [ ] Thread through all functions as a parameter
- [ ] Keep a `_default_ctx` module-level instance for backward compat
- [ ] Run pytest — must be green
- [ ] Run head2head — must be identical behavior (score ~50%)
- [ ] **Commit this separately** — it's the highest-risk step

### Phase 2: Move files (mechanical)
- [ ] Create target directory with `__init__.py`
- [ ] Move the file
- [ ] Leave a backward-compat SHIM at the old location:
  ```python
  # Backward-compat shim — real module lives in draughts.app now
  from draughts.app.controller import GameController, AIWorker  # noqa: F401
  ```
- [ ] Update direct importers (grep for the old path)
- [ ] Run pytest — must be green
- [ ] **Commit per moved file**

### Phase 3: Split large files
- [ ] Map the dependency graph within the file (which function calls which)
- [ ] Find the ACYCLIC cut — the split that creates NO circular imports
  - state.py ← tt.py ← eval.py ← moves.py ← search.py (one-way)
- [ ] Create sub-package: `target/__init__.py` with re-exports
- [ ] Move functions to sub-modules, adding intra-package imports
- [ ] Delete the old flat file (Python resolves package over file)
- [ ] `__init__.py` must re-export EVERY public symbol for compat
- [ ] Also re-export commonly-used private symbols (`_search_best_move`)
- [ ] For attribute access on the module (`ai._last_search_score`),
      add `__getattr__` to `__init__.py`
- [ ] Run pytest — must be green
- [ ] Run head2head — must be identical
- [ ] **One commit for the entire split**

### Phase 4: Extract concerns
- [ ] Move `Analysis` dataclass to its own module
- [ ] Replace side-channel globals with clean return values
- [ ] Add new tests for the extracted module
- [ ] **Commit per extraction**

## Import invariants to enforce

| Package | May import | Must NOT import |
|---|---|---|
| `config` | stdlib, numpy | anything in draughts |
| `game/ai/` | `config`, `game/board`, numpy | `app/`, `ui/`, `engine/` |
| `game/` (other) | `config`, `game/ai/`, numpy | `app/`, `ui/` |
| `engine/` | `config`, `game/`, stdlib | `app/`, `ui/`, **PyQt6** |
| `app/` | `config`, `game/`, `engine/`, PyQt6 | `ui/` |
| `ui/` | everything | — |
| `tools/` | `config`, `game/`, Pillow | PyQt6 |

Verify with:
```python
# Test: engine/ has no Qt dependency
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-c", "from draughts.engine import EngineSession"],
    capture_output=True, text=True
)
assert result.returncode == 0
```

## Common pitfalls

1. **Python resolves packages before files.** If you create
   `draughts/game/ai/` (directory), the old `draughts/game/ai.py`
   (file) MUST be deleted. Both cannot coexist.

2. **`__init__.py` must re-export for backward compat.** Old code
   doing `from draughts.game.ai import AIEngine` must still work.
   Use explicit re-exports, not `from .search import *`.

3. **`__getattr__` for module-level attribute access.** Code doing
   `ai._last_search_score` won't work with a package unless you add
   `__getattr__` to `__init__.py` that delegates to the right sub-module.

4. **Circular imports are the #1 risk.** If `eval.py` imports from
   `search.py` AND `search.py` imports from `eval.py` → ImportError.
   Solution: put shared types in `state.py` (no internal imports).

5. **Test this before committing:**
   ```bash
   grep -rn "from draughts.game.ai import" draughts/ tests/ | head -30
   ```
   Every hit must resolve correctly with the new layout.
