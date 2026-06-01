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
the skill makes it:

1. **Declare** the required set in code (`required = set(range(200, 251))`, the
   five region names, the invoice IDs, …).
2. **Verify by execution** — write and run code that parses what's present and
   computes `required − present`.
3. **Gate**: if the gap is non-empty, abstain and report the exact missing items;
   if empty, proceed and do the deterministic work (sums/joins/counts) in code too.

The only step left to the LLM is translating the task's language into a concrete
required set — an easy, checkable step, unlike judging completeness.

## When it helps

- RAG / top-k retrieval that may not cover everything the task needs.
- Truncated dumps, partial exports, multi-file joins.
- Any task where "I'm missing X" is a better answer than a confident wrong number.

## When it won't fire (by design)

- The full source is clearly, completely present.
- Open-ended generation with no completeness requirement.
- No well-defined required set to diff against.

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
