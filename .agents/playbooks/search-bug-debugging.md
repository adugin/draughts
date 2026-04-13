# Playbook: Debugging Search Bugs in Minimax Engines

**When to use:** AI makes obviously wrong moves, eval seems incorrect,
search returns unexpected scores, blunder rate is too high.

## The technique (proven on the quiescence fail-hard bug)

### Step 1: Isolate a specific bad position
Find a concrete position where the AI makes a provably wrong move.
Use heartbeat logs (`--heartbeat`) to find eval swings > 10.

```bash
python dev.py play-game --games 10 --difficulty 2 --depth 5 \
  --heartbeat .planning/reports/hb_debug.log -v
```

Grep for big swings, extract the position at that ply.

### Step 2: Reproduce deterministically
```python
game = HeadlessGame(auto_ai=False)
# ... replay to the suspect position ...
# Then ask the AI:
move = _search_best_move(board, color, depth=5)
```
Seed `random.seed(0)` and `ai._default_ctx.clear()` for determinism.

### Step 3: Compare direct _alphabeta vs _search_best_move
This is the KEY diagnostic. If they disagree, the bug is in the
iterative deepening / move selection logic:

```python
# Direct call on each root move:
for kind, path in moves:
    child = _apply_move(board, kind, path)
    ai._default_ctx.clear()
    score = _alphabeta(child, depth-1, -inf, +inf, False, opp, color,
                       ctx=SearchContext())
    print(f"{notation}: {score}")

# Compare with _search_best_move result:
ai._default_ctx.clear()
move = _search_best_move(board, color, depth)
print(f"search picks: {move} score={ai._last_search_score}")
```

### Step 4: Sweep alpha to find clamping
If scores seem wrong, test whether they're being clamped to alpha:

```python
for alpha in [-30, -10, -5, 0, 0.29, 1, 5, 10]:
    ai._default_ctx.clear()
    r = _alphabeta(child, depth, alpha, float('inf'), False, color, color,
                   ctx=SearchContext())
    print(f"alpha={alpha:+.2f} -> {r:+.4f}")
```

If the result equals alpha for all values → **fail-hard bug**.
The function returns the bound instead of the actual score.

### Step 5: Trace iterative deepening depth by depth
```python
for depth in range(1, 6):
    for kind, path in moves:
        child = _apply_move(board, kind, path)
        score = _alphabeta(child, depth-1, alpha, beta, False, opp, color)
        print(f"d={depth} {notation}: {score}")
```

Check: does a move that's clearly bad at depth 2 suddenly look
"good" at depth 3+? That's TT pollution or alpha-bound leakage.

### Step 6: Check TT interaction
Clear TT between depth iterations to isolate TT effects:
```python
ctx = SearchContext()
ctx.tt.clear()  # between each depth
```

If clearing TT fixes the score → TT is caching a wrong value
(wrong flag, wrong depth, cross-root-color pollution).

## Red flags to watch for

| Symptom | Likely cause |
|---|---|
| All root moves return the SAME score | Fail-hard quiescence clamping to alpha |
| Score equals alpha exactly | Alpha-bound returned instead of true value |
| Score correct at depth N, wrong at N+1 | TT pollution from depth N stored with wrong flag |
| Different results with clean vs dirty TT | TT cross-contamination between depth iterations |
| Move is legal but obviously bad | Search saw a different position (board copy bug?) |
| Blunder rate high but no crashes | Silent semantic bug — worst kind |

## Previous bugs found with this technique

1. **Quiescence fail-hard** (BUG of the project): `return alpha`
   instead of `return stand_pat`. All root moves tied at alpha.
   random.choice picked blunders. 29% blunder rate was "normal".
2. **Off-diagonal penalty regression**: seed bench showed -19 eval
   drop. Traced to king_distance_score returning 0 for most targets.
3. **Depth boost timeout**: L6 (depth 8+2=10) hitting move_timeout.
   Traced via perf_baseline showing endgame 4x slower.
