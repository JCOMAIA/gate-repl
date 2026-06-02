# beliefgate

Verify that a context actually contains everything a task requires — **before**
answering — and refuse with the exact gap rather than answering over incomplete
data. The core guarantee, enforced by tests: **the gate never returns COMPLETE for
context that isn't complete.** It errs only toward refusal.

Zero runtime dependencies. Pure stdlib. Domain-agnostic: you bring the data and
(optionally) the LLM; the library is the deterministic part that carries the safety
guarantee.

```python
from beliefgate import check_set

res = check_set(required=range(200, 251), present=present_ids)
if res.ok:
    answer = compute(...)          # safe: coverage proven
else:
    print(res)                     # "INCOMPLETE: missing [225] (...)"
    # abstain, or fetch the missing items from the source — never guess
```

## Why it exists

LLMs (and people) judge completeness at *summary granularity* — "IDs 300–320 look
present" — and miss interior holes (310 is actually gone). Completeness is not a
judgment; it's a computation: the requirement is a set, the context is a set, the
gap is a **set difference**, which cannot miss an interior element. This library
moves that decision (and harder coverage decisions) out of judgment and into
verifiable code.

The guarantee is asymmetric on purpose: refusing a valid task is tolerable;
certifying an invalid one is catastrophic. The gate only ever makes the tolerable
error.

## Install

```bash
pip install -e .            # from this directory
# or copy the beliefgate/ package into your project — it has no dependencies
```

Run the tests (they ARE the safety guarantee):

```bash
python -m pytest beliefgate/tests/ -q
# or, without pytest:
PYTHONPATH=. python beliefgate/tests/test_beliefgate.py
```

## Two levels

### 1. Enumerable set — the common case

When the requirement is an explicit set of keys (an ID range, twelve months, a list
of invoices). Keys can be any hashable: ints, strings, dates, tuples.

```python
from beliefgate import check_set

required = {f"INV-{n}" for n in range(100, 121)}      # what the task needs
present  = extract_invoice_ids(context)               # what you actually have
res = check_set(required, present)

if res.ok:
    total = sum_invoices(context)
else:
    # res.missing == ["INV-102", ...] — the exact gap, not "looks incomplete"
    abstain(missing=res.missing)
```

`res.verdict` is `COMPLETE` or `INCOMPLETE`; `res.missing` lists the exact missing
keys; `res.ok` is `True` only when complete.

### 2. Predicate coverage — the advanced case

When the requirement is a *predicate* ("all sales > 5000") with no a-priori set.
Completeness becomes coverage: *have I seen every record the predicate could
select?* This is decidable only under a **deletion-proof invariant** on the source.

```python
from beliefgate import (CoverageClaim, CoverageKind, SourceFacts, verify_coverage)

facts = SourceFacts(
    present_count=len(records),        # records you actually have
    keys=[r.id for r in records],      # for contiguity checks
    sorted_desc=is_sorted_desc(records),
    boundary_crossed=min_value(records) <= 5000,
    predicate_evaluable=True,          # can you evaluate "> 5000" from the records?
)

# You (or an LLM) declare WHICH invariant the source justifies:
claim = CoverageClaim(CoverageKind.FULL_COUNT, total=source_claimed_total)
res = verify_coverage(claim, facts)    # COMPLETE / INCOMPLETE / UNDECIDABLE
```

**The invariants and what they prove:**

| `CoverageKind` | proves | deletion-proof? |
| :--- | :--- | :---: |
| `FULL_COUNT` | `present_count == source's claimed total` | ✅ yes |
| `CONTIGUOUS_IDS` | keys form a gapless range (nothing deleted within) | ✅ yes |
| `SORTED_TO_THRESHOLD` | sorted + boundary crossed | ❌ **no** — a mid-deletion leaves it sorted |
| `NONE` | nothing applies | — |
| `UNDECIDABLE` | the predicate can't be evaluated from the records at all | — |

The verifier runs two gates: (a) is the kind deletion-proof? (b) does it hold in
the data? It certifies COMPLETE only if both. `UNDECIDABLE` is returned when the
predicate needs a field that isn't in the records (e.g. an external "flagged"
status) — distinct from a proven gap.

### Wrapping an LLM to declare the claim (with repair)

If an LLM declares the coverage claim, it can slip (put the answer value in `total`)
or err (`undecidable` for a decidable predicate). The repair loop catches both and
asks it to fix — without ever weakening the guarantee.

```python
from beliefgate import run_with_repair, CoverageClaim, CoverageKind

def my_declare_fn(facts, source_total, repair_msg):
    prompt = build_prompt(facts, repair_msg)   # YOUR prompt, YOUR LLM SDK
    raw = call_your_llm(prompt)
    kind, total = parse_declaration(raw)        # -> CoverageKind, int|None
    return CoverageClaim(kind, total)

res, trace = run_with_repair(my_declare_fn, facts, source_total=200)
# trace shows each attempt + the diagnostic that drove the repair
```

**One invariant you must respect when wrapping an LLM:** on repair, the corrected
`total` must come from the **source's claimed total** (its label/metadata), never
from the count of records you currently see. Otherwise partial data would be
"repaired" into a false COMPLETE. The library passes you `source_total` for exactly
this; use it.

## The load-bearing rule (read this first)

> **Feed `present` from a STRUCTURED source, not from an LLM transcribing prose.**

The library's core (set difference / coverage verification) is deterministic and
fail-safe. But *something* must produce the `present` set from your real data. If
that something is an LLM listing keys it reads out of messy text or a prose table,
you have re-introduced the judgment the gate exists to remove — at the edge — and
the guarantee blurs (we measured this: an LLM extractor brittle on long, near-
identical table headers caused both false-positives and false-alarms; the core was
never at fault).

So the gate **shines** when `present` comes from a parser, a DB query, an API, or
a deterministic scan of a known format (`ID_207:` lines, JSON rows, table columns
by exact header) — and the **required** set comes from the TASK (an id range,
named months/columns, a list of invoices), so the key survives even when the datum
is missing. When relevance is only knowable by *understanding* the data (open QA),
the gate needs a relevance oracle it doesn't have and should be paired with an LLM,
not used alone.

## How to adapt to YOUR domain

The library never parses your data — that keeps it domain-agnostic. You write the
small adapter that turns your context into sets / facts. Checklist:

1. **Identify the requirement.**
   - A known set of keys? → use `check_set`. Define `required` from the task
     ("orders 100–150" → `set(range(100, 151))`; "all five regions" → the five
     names).
   - A predicate? → use `verify_coverage`. The qualifying set isn't known up front.

2. **Parse `present` from your context** — robustly. Whatever your record format
   (JSON rows, log lines, DB result, prose), extract the keys. Be liberal: a record
   present in a noisy format still counts as present.

3. **For predicates, establish a deletion-proof invariant.** Ask: what does the
   *source* guarantee? An authoritative count? Sequential IDs? If the only thing you
   have is "it's sorted", that is **not** enough — declare `SORTED_TO_THRESHOLD` and
   the gate will (correctly) refuse. Get a count or contiguity, or accept refusal.

4. **Wire `predicate_evaluable` honestly.** Can the predicate be computed from the
   fields you have? If it depends on something external (a flag from another
   system), set it `False` and the gate returns `UNDECIDABLE` — which is the correct
   answer, not a failure.

5. **On `INCOMPLETE`/`UNDECIDABLE`, never fill the gap by guessing.** Either fetch
   the missing items from the real source and re-check, or abstain and report what's
   missing (`res.missing`, `res.reason`). Interpolating, averaging, or assuming zero
   silently corrupts the answer — the whole point is to not do that.

## API summary

| name | use |
| :--- | :--- |
| `check_set(required, present)` | enumerable-set completeness → `GateResult` |
| `verify_coverage(claim, facts)` | predicate coverage → `GateResult` |
| `run_with_repair(declare_fn, facts, source_total)` | LLM-declared coverage with repair → `(GateResult, trace)` |
| `check_consistency(claim, facts, source_total)` | is a declaration coherent? → `Consistency` |
| `Verdict` | `COMPLETE` / `INCOMPLETE` / `UNDECIDABLE` |
| `GateResult` | `.verdict`, `.missing`, `.reason`, `.ok` |
| `CoverageKind`, `CoverageClaim`, `SourceFacts` | predicate-coverage inputs |

## The method behind it

This library is the packaged result of an empirical study (`docs/GATE_REPL.md` in
the parent repo): an LLM judging completeness false-passes on subtle interior gaps
(7/15, 2/15 across models); moving the check into executed code drops that to 0/15,
holds across models and noisy data, extends to predicate coverage, and never
false-completes. The library is the deterministic core of that result — the part
that carries the guarantee, with the LLM left as a pluggable, checkable declarer.

MIT licensed.
