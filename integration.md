# Integrating belief-gate into a pipeline

A practical guide to wiring `beliefgate` into real systems — custom pipelines, MCP
servers, Claude Code, agent loops — with honest guidance on where it earns its
keep and where it doesn't.

> **The one rule that determines success:** feed `present` from a STRUCTURED source
> (a parser, a DB query, an API response), and derive `required` from the TASK (an
> id range, named columns, a list of keys). Inside that envelope the guarantee is
> absolute — the gate never certifies an answer it can't prove complete. Outside it,
> the gate degrades to whatever produced its inputs.

---

## 1. What the gate actually does (and doesn't)

It answers ONE question, deterministically: **does the context contain every item
the task requires?** It returns `COMPLETE` (proceed), `INCOMPLETE` (here is the
exact gap), or `UNDECIDABLE` (can't tell from what's available). It never returns
`COMPLETE` for incomplete context — verified leak-proof, cross-model.

It does **not** answer the question, retrieve anything, rank relevance, or judge
meaning. It is a gate you put *before* an expensive or irreversible step, so that
step never runs on incomplete data.

```python
from beliefgate import check_set

res = check_set(required={"2021", "2022", "2023"}, present=columns_in_table)
if res.ok:
    answer = compute_totals(table)          # safe: all required years present
else:
    abstain(res.missing)                     # e.g. ["2022"] — fetch it or refuse
```

---

## 2. Where it shines vs. where it doesn't

### Shines (use it)

| Situation | Why |
| :--- | :--- |
| Multi-source numeric aggregation ("sum tax over A 200–250 + B 400–450") | Required ranges come from the task; presence is parseable; a missing row is invisible to eyeballing but caught by set difference |
| Required set is **enumerable from the task** | id ranges, the 12 months, a fixed list of invoices/regions/SKUs |
| `present` comes from a **structured source** | DB rows, API fields, CSV columns, parsed log keys |
| A wrong answer is worse than "I don't have enough" | finance, audit, compliance, anything that ships code or moves money |
| You want a cheap pre-flight before an expensive call | the gate's set difference is ~free vs. a 100k-token compute |

### Doesn't (don't force it)

| Situation | Why it fails / what to use |
| :--- | :--- |
| Open QA ("what does this contract say about X?") | Relevance isn't enumerable from the task; the gate would need an oracle it doesn't have. Use an LLM. |
| `present` must be read from messy prose by an LLM | Measured bottleneck: the LLM-extractor mis-transcribes; the gate then over-abstains or mismatches. The core is fine; the edge isn't. |
| The required key only exists by *seeing* the data | If a dropped item's key vanishes with it, the gate can't name what's missing. |
| Subjective / semantic properties (tone, intent, "is this a decision?") | No deterministic anchor. The gate is for completeness, not meaning. |
| The task is small and obviously complete | No subtle gap to catch; you're adding latency for nothing. |

**Rule of thumb:** the gate is for *"did I get all of a known set?"*, not *"is this
relevant / correct / well-written?"*.

---

## 3. The integration shape (same everywhere)

Every integration is three steps. Only steps 1 and 2 are yours; step 3 is the lib.

```
1. REQUIRED  = the set the task needs        ← from the task / question (you)
2. PRESENT   = the keys actually in context  ← from a parser / DB / API (you)
3. VERDICT   = check_set(REQUIRED, PRESENT)  ← the library (deterministic)
   → COMPLETE: run the expensive/irreversible step
   → INCOMPLETE: abstain with res.missing, or fetch the gap and re-check
```

The library never parses your data — that is deliberate (it stays domain-agnostic
and the safety guarantee can't be undermined by a bad parser hidden inside it). You
own the two adapters; they are usually ~10 lines each.

---

## 4. Custom pipeline (plain Python)

A retrieval-then-answer pipeline that refuses to answer over incomplete retrieval.

```python
from beliefgate import check_set, Verdict

def answer_quarterly_report(question, retriever, db):
    # 1. REQUIRED — parse the task into an explicit set
    quarters = extract_quarters(question)        # e.g. {"Q1-2023","Q2-2023","Q3-2023"}

    # 2. PRESENT — from a STRUCTURED source, not an LLM
    rows = db.query("SELECT quarter FROM revenue WHERE quarter IN :qs", qs=quarters)
    present = {r.quarter for r in rows}

    # 3. VERDICT
    gate = check_set(required=quarters, present=present)
    if not gate.ok:
        return {
            "status": "insufficient",
            "missing": gate.missing,             # ["Q2-2023"]
            "message": f"Cannot compute: missing data for {gate.missing}. "
                       f"Fetch it and retry — I won't guess.",
        }

    # only now do the expensive / committing work
    total = sum(db.revenue(q) for q in quarters)
    return {"status": "ok", "total": total}
```

The win: `answer_quarterly_report` *cannot* return a confident wrong total when a
quarter is missing from the DB. It abstains with the exact gap.

### Recovery instead of abstention

If a source can supply the missing items, recover deterministically — read the real
value, never estimate:

```python
gate = check_set(required, present)
if not gate.ok:
    recovered = {q: db.fetch(q) for q in gate.missing if db.has(q)}
    present |= set(recovered)
    gate = check_set(required, present)          # re-check after recovery
    if not gate.ok:
        return abstain(gate.missing)             # still missing -> refuse
```

---

## 5. Predicate coverage (when "required" isn't a fixed list)

For tasks like "sum all sales above 5000", there's no a-priori set. Completeness
becomes a *coverage* question, decidable only under a **deletion-proof invariant**.
You (or an LLM you wrap) declare which invariant the source justifies; the lib
verifies it.

```python
from beliefgate import CoverageClaim, CoverageKind, SourceFacts, verify_coverage

facts = SourceFacts(
    present_count=len(rows),
    keys=[r.id for r in rows],
    sorted_desc=is_sorted_desc_by_amount(rows),
    boundary_crossed=min(r.amount for r in rows) <= 5000,
    predicate_evaluable=True,        # can "> 5000" be evaluated from the rows?
)
# the source claims it's the complete table of 200 rows:
claim = CoverageClaim(CoverageKind.FULL_COUNT, total=source_claimed_total)
res = verify_coverage(claim, facts)
# COMPLETE only if the claim is deletion-proof AND holds in the data.
```

Key fact you must respect: **`sorted + boundary crossed` is NOT deletion-proof** — a
record deleted from the middle leaves the list sorted. Only `FULL_COUNT` or
`CONTIGUOUS_IDS` prove no qualifying record is missing. The lib enforces this; if you
declare `SORTED_TO_THRESHOLD` it will (correctly) refuse to certify.

If an LLM declares the claim, wrap it in the repair loop so a mis-declaration is
caught and corrected instead of silently trusted:

```python
from beliefgate import run_with_repair

def my_declarer(facts, source_total, repair_msg):
    raw = call_your_llm(build_prompt(facts, repair_msg))
    kind, total = parse(raw)
    return CoverageClaim(kind, total)

res, trace = run_with_repair(my_declarer, facts, source_total=200)
```

> On repair, the corrected `total` must come from the **source's claimed total**,
> never from the count of rows you currently see — otherwise partial data gets
> "repaired" into a false COMPLETE. The lib passes you `source_total` for exactly
> this.

---

## 6. MCP server (expose the gate as a tool)

Wrap the gate as an MCP tool so any MCP-capable agent can call it before acting. The
agent supplies `required` (from its task) and the server computes `present` from the
real source it owns.

```python
# pseudo-MCP server — adapt to your MCP SDK (FastMCP shown in spirit)
from beliefgate import check_set

@mcp.tool()
def verify_complete(required: list[str], source: str) -> dict:
    """Verify a data source contains every required key before the agent computes.
    Returns {complete, missing, reason}. Never claims complete when it isn't."""
    present = load_present_keys(source)          # YOUR structured loader (DB/file/API)
    res = check_set(required=required, present=present)
    return {"complete": res.ok, "missing": res.missing, "reason": res.reason}
```

Now an agent's flow becomes: *call `verify_complete` → if not complete, fetch the
missing keys or tell the user → only then compute.* The determinism lives
server-side, so the agent can't talk itself past a real gap. Because the tool returns
the **exact missing set**, the agent also knows precisely what to fetch next.

**Design note:** keep `load_present_keys` deterministic (parse the source, don't ask
a model what's in it). That's the line between the gate working and the gate
inheriting an LLM's transcription errors.

---

## 7. Claude Code (the skill, no Python needed by the user)

For Claude Code there are two routes:

**A. The packaged skill** (`plugins/belief-gate/`). Claude applies the discipline
using its own code execution — it writes and runs the set-difference check rather
than eyeballing completeness. Install by pointing Claude Code at the plugin dir, or
drop `SKILL.md` into `.claude/skills/belief-gate/`. Use it when a task is "verify I
have all of X before computing." See the plugin's README.

**B. Import the lib in a Claude Code session.** If the project already has
`beliefgate` installed, just tell Claude to use it:

> "Before summing, use beliefgate.check_set with the required quarters from the
> question and the quarters present in the parsed table; abstain on any gap."

Claude then runs deterministic verification instead of judging completeness in
prose. This is the faithful pattern: the LLM (Claude) declares the required set from
the task and parses present from the file; the lib's set difference makes the call.

---

## 8. Agent loop (gate before an irreversible action)

The highest-value placement: a gate immediately before any step that's expensive,
external, or hard to undo (a payment, a PR, a DB write, a customer-facing answer).

```python
def agent_step(task, context):
    required = derive_required(task)             # from the task
    present  = parse_present(context)            # structured
    gate = check_set(required, present)
    if not gate.ok:
        # do NOT take the action; ask, fetch, or abstain
        return request_missing(gate.missing)
    return take_irreversible_action(task, context)
```

The asymmetry that makes this worth it: refusing a valid action is recoverable (you
retry); taking an action on incomplete data is often not (the wrong PR ships, the
wrong total is invoiced). The gate only ever makes the recoverable error.

---

## 9. Anti-patterns (things that quietly break the guarantee)

- ❌ **Letting an LLM produce `present` by reading prose.** Measured failure mode —
  the model mis-lists keys, the gate over-abstains or mismatches. Parse the source.
- ❌ **Deriving `required` from the data instead of the task.** If "what's required"
  depends on seeing the data, you've reintroduced the relevance judgment the gate
  can't do.
- ❌ **Declaring `SORTED_TO_THRESHOLD` and expecting a COMPLETE.** Sorting isn't
  deletion-proof; the gate refuses by design. Get a count or contiguity.
- ❌ **Filling a gap with zero / average / interpolation on INCOMPLETE.** The whole
  point is to not do this. Recover from a real source or abstain.
- ❌ **Using it for relevance, correctness, tone, or "is this a decision?"** No
  deterministic anchor; wrong tool.
- ❌ **On repair, computing `total` from rows you can see.** Use the source's claimed
  total, or a partial source "repairs" into a false COMPLETE.

---

## 10. Quick reference

| Need | Call |
| :--- | :--- |
| Is a known set fully present? | `check_set(required, present) -> GateResult` |
| Does a predicate query have provable coverage? | `verify_coverage(claim, facts) -> GateResult` |
| LLM declares the coverage invariant, with safety net | `run_with_repair(declare_fn, facts, source_total)` |
| Read a verdict | `res.ok`, `res.verdict` (`COMPLETE`/`INCOMPLETE`/`UNDECIDABLE`), `res.missing`, `res.reason` |

**Install:** `pip install -e .` from the lib dir, or copy the `beliefgate/` package
(zero runtime dependencies). **Tests are the guarantee:** `python -m pytest
beliefgate/tests/ -q` — the leak-proof tests prove the gate never false-completes.

For the method and evidence behind all this, see `docs/GATE_REPL.md`; for where the
discipline does and doesn't generalize, `docs/UNIFICATION.md`.
