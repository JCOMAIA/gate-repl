# belief-gate (Claude Code plugin)

A Claude Code skill that makes Claude **verify context completeness by executing
code** before answering grounded questions — instead of eyeballing whether the
context "looks complete". It prevents confident wrong answers (confabulation)
over incomplete retrieved/pasted data.

## The idea in one sentence

Completeness is computation, not judgment: declare what the task requires as a
set, parse what the context actually contains, and let a **set difference** decide
— because a set difference cannot miss an interior gap, but range-judgment
routinely does.

This is the applied, inference-time version of the gate-REPL result in this repo
(`docs/GATE_REPL.md`): an LLM judging completeness false-passed 7/15 on subtle
gaps; moving the check into executed code dropped that to 0/15.

## Install / test locally

From the repo root:

```bash
claude --plugin-dir ./plugins/belief-gate
```

The skill is model-invoked — Claude uses it automatically when a task involves
answering from retrieved or provided context that might be incomplete. You can
also nudge it explicitly:

> Using the belief-gate approach, compute the total from this retrieved data: ...

Run `/reload-plugins` after editing the skill during development.

## What it does, concretely

When Claude answers from context (RAG results, a pasted document, a query dump),
the skill makes it do **two** deterministic moves:

1. **Declare** the required set in code (`required = set(range(200, 251))`, the
   five region names, the invoice IDs, …).
2. **Gate by execution** — write and run code that parses what's present and
   computes `required − present`; if the gap is non-empty, abstain with the exact
   missing items.
3. **Compute by execution** — if the gate passes and the work is deterministic
   (sums/joins/counts), run *that* in code too. Measured: strong models score
   3–6/80 on multi-cell financial sums (one model 0/40) — the LLM is the wrong tool
   for exact arithmetic; the CPU does it perfectly and free.

The only step left to the LLM is translating the task's language into a concrete
required set — an easy, checkable step, unlike judging completeness or doing the sum.

It also covers a **predicate-coverage** variant ("sum everything above X" — provable
only under a deletion-proof invariant) and, if the `beliefgate` library is installed,
will use its tested `check_set` / `verify_coverage` / `verify_fresh` primitives.

## When it helps (the measured regime)

- The task **aggregates/computes** over context (a total, a join, a reconciliation),
  where a silently missing slice yields a confident wrong number — measured at **35%**
  on a strong model.
- RAG / top-k retrieval, truncated dumps, partial exports, multi-file joins.
- Any task where "I'm missing X" is a better answer than a confident wrong number.

## When it won't fire (by design — measured)

- **Single-fact lookup** with an abstention option: models already self-abstain
  (~0% confabulation measured); a gate adds nothing.
- The full source is clearly, completely present.
- Open-ended generation, or relevance/meaning with no enumerable required set.

## Reproducing the underlying benchmark

This plugin ships the *technique*, not the experiment. To see the 7/15 → 0/15
result yourself, use the benchmark in the repo (`bench/proto_gate_adv.py` and
`bench/proto_gate_repl.py`) — see `docs/GATE_REPL.md` for the full method and
how to run it.

## Safety note

The technique relies on executing code (Claude's Bash/python tools). That code
parses context you provide; review it as you would any executed code. The
benchmark's REPL is a bare `exec()` and is not sandboxed — fine for local use,
not for untrusted input.
