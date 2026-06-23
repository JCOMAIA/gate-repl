# Agent-built Unity levels with a deterministic "done" gate

A worked sketch of the idea: a **deterministic manifest** (the contract) + an **agentic build
loop** (Claude Code driving a Unity MCP) + a **belief-gate check** that gives the loop a
*checkable* termination condition instead of the agent's opinion that it "looks finished".

Files:
- `level_manifest.json` — the contract: what assets, where, with which properties/relations,
  and which playability invariants must hold.
- `scene_gate.py` — the deterministic verifier (runnable demo, no Unity needed). Presence by
  set-difference (belief-gate core) + reachability invariants over a jump-graph. Returns the
  *exact* gap.

```
$ python scene_gate.py
SCENE B — agent forgot plat_f and misplaced coin_2:
  • place missing objects: ['plat_f']
  • move coin_2 to [24, 9] (currently [24, 14], off by 5.0)
  • playability: exit not reachable from spawn (jump-graph disconnected)
```

## The build loop (pseudocode)

```
manifest = load("level_manifest.json")          # the contract you wrote ONCE
budget   = 8                                     # retry budget (circuit breaker)

for attempt in 1..budget:

    # 1. BUILD — the probabilistic step (Claude Code via Unity MCP)
    agent.build_or_fix(manifest, last_gap)       # places/moves objects in the scene

    # 2. QUERY — read the REAL scene, not the agent's claim   <<< the load-bearing rule
    present = unity_mcp.query_scene()            # [{id, type, pos}, ...] from the hierarchy

    # 3. GATE — deterministic verification
    report = gate(manifest, present)             # required − present  +  invariants

    # 4. DECIDE — checkable termination, not vibes
    if report.complete:
        return DONE                              # gap == ∅  AND  playability holds
    last_gap = format_gap(report)                # the exact missing/misplaced/unreachable list

# 5. CIRCUIT BREAKER — never loop forever
commit_evidence(last_gap); halt(); notify_human()   # stuck after `budget` tries → escalate
```

The agent only ever sees the **precise gap** as its next instruction, and "done" is a fact
(`required − present == ∅` and invariants pass), never a self-assessment. That is the whole
point: it removes the #1 failure of agentic building — the agent declaring victory on a scene
that is incomplete or unplayable.

## Why this is a good fit (and what it does NOT do)

**Does (deterministic, real value):**
- A **checkable termination condition** for the loop — the agent can't "finish" a broken scene.
- Catches **missing objects, wrong placements, broken/unreferenced assets** (set difference).
- Catches **unplayable layouts** — e.g. dropping one platform makes the exit unreachable; the
  reachability invariant flags it even though every *object* might still be present.
- The gap is a **perfect prompt** for the next iteration (exact, structured).
- Automates the **tedious execution** of a design you specify (write the contract once, let the
  loop grind), with a guarantee it's complete.

**Does NOT (be honest):**
- It does **not design the level for you.** The manifest carries your taste; the gate only
  checks the build matches it. A boring spec → a faithfully-built boring level.
- It does **not judge "fun" or animation quality** — only enumerable structure and playability
  invariants you can express as code.
- It is only as strong as the manifest is **specific.** `{type: Platform}` checks presence;
  add `pos` and it checks placement; add relations/invariants and it checks playability.
  Vague contract → weak gate (it catches *absence*, not a *wrong-but-present* choice — unless
  you put the constraint in the contract).

## The one rule you cannot break

> `present` must be **read from the actual scene** (the Unity hierarchy — the structured
> source), **never** from the agent's prose ("I placed everything").

Trusting the self-report puts an LLM back in the judgment seat and reintroduces exactly the
false-pass the gate exists to remove. The gate's guarantee is leak-proof *only* because both
sides of the difference (`required` from the contract, `present` from the scene) are
deterministic. This is the same rule the project measured elsewhere: feed `present` from a
parser/DB/API, not from a model reading text (`docs/GATE_REPL.md` §11.3).

## Extending it
- More invariants are just more deterministic checks: no overlapping colliders, navmesh
  coverage, every Animator state has a valid exit transition (a coverage check, like the
  predicate gate in `docs/GATE_REPL.md` §10), difficulty budget (count of hazards in range).
- The same loop shape works for any agent-built artifact with an enumerable contract — not
  only Unity scenes.
