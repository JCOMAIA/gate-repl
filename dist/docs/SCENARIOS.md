# belief-gate / gate-REPL — real usage scenarios

The gate is abstract until you see *what goes wrong without it*. Each scenario below
shows the silent failure first, then the gate fix. The through-line, learned from the
benchmarks: **the gate earns its keep in the compute / aggregate / multi-fact regime,
where models confabulate confidently — not in single-fact lookup, where they self-abstain.**

The library exposes three capabilities; the scenarios map to them:

| Capability | Question it answers | API |
| :--- | :--- | :--- |
| Set gate | "Is every required item present *right now*?" | `check_set(required, present)` |
| Coverage gate | "Does a predicate query provably cover everything?" | `verify_coverage(claim, facts)` |
| Bookkeeping memory | "Is this cached/derived value still current?" | `remember` / `verify_fresh` |

---

## Scenario 1 — Quarterly revenue close (the canonical case)

**Setting.** A finance assistant answers: *"What was total revenue across all regions for
2024?"* The data comes from a warehouse export, region by region. The North-America extract
failed silently this morning, so the context has 4 of 5 regions.

**Without the gate.** The LLM sums the 4 regions it can see and reports a confident total —
off by the entire North-America number. Nobody notices: the answer *looks* complete, the
prose is fluent. (This is exactly the failure we measured: on aggregation with a silently
dropped slice, gemini-2.5 confabulated a wrong total **35%** of the time.)

**With the gate.**
```python
from beliefgate import check_set

required = {"NA", "EMEA", "APAC", "LATAM", "MEA"}      # the 5 regions the task names
present  = {row.region for row in warehouse_rows}       # parsed from the export (structured)

gate = check_set(required, present)
if not gate.ok:
    return f"Cannot total 2024 revenue: missing region data for {gate.missing}. " \
           f"Re-run the extract — I won't estimate."     # -> ['NA']
total = sum(r.amount for r in warehouse_rows)            # only runs when provably complete
```
**Payoff.** The wrong total is impossible. The assistant names the exact gap (`NA`) instead
of shipping a number that's silently $X billion light.

---

## Scenario 2 — RAG that refuses to answer over partial retrieval

**Setting.** A support bot answers policy questions from a knowledge base via top-k
retrieval. A question needs all 4 sub-clauses of the refund policy, but the retriever
returned only 3 chunks (the 4th lost to the similarity cutoff).

**Without the gate.** The LLM composes a confident, *incomplete* policy answer from 3
clauses. The missing clause is the one with the exception that applies to this customer.

**With the gate.** You know the policy is structured into sections, so the task can name them:
```python
required = {"eligibility", "window", "exceptions", "process"}   # the 4 clauses this Q needs
present  = {chunk.section_id for chunk in retrieved}            # tagged at index time

gate = check_set(required, present)
if not gate.ok:
    fetch_sections(gate.missing)        # ['exceptions'] — go get it, then re-check
    # or escalate to a human; do NOT answer on 3/4
```
**Payoff.** The bot recovers the missing clause (or abstains) instead of giving a
plausible-but-wrong policy. The gate turns "top-k returned something" into "top-k returned
*everything this task needs*."

---

## Scenario 3 — Invoice / payment reconciliation

**Setting.** Month-end: *"Have all 312 invoices from the PO system been paid?"* You have a
payments export.

**Without the gate.** The LLM (or a human skimming) eyeballs the list, sees a long run of
paid invoices, and says "looks complete." Three invoices in the middle were never matched.

**With the gate.**
```python
required = {inv.id for inv in po_system.open_invoices()}   # 312 ids — from the source of truth
present  = {p.invoice_id for p in payments_export}          # ids actually paid

gate = check_set(required, present)
#  gate.ok        -> all 312 reconciled
#  gate.missing   -> exactly the unpaid ids, e.g. [INV-2207, INV-2251, INV-2290]
```
**Payoff.** Set difference cannot miss an interior gap the way eyeballing a sorted list
does. You get the precise unpaid set, every time, for free.

---

## Scenario 4 — "Sum everything above the threshold" (coverage, not a fixed set)

**Setting.** *"Total of all transactions over $10,000 this quarter."* Here you can't
enumerate the required ids in advance — the qualifying set depends on the data. A page of
results came back; is it the *whole* qualifying set, or just the first page?

**Without the gate.** The LLM sums the page it received and reports a total. If the API
paginated and you only passed page 1, the total is partial — and looks authoritative.

**With the gate (coverage).** Completeness is only provable under a *deletion-proof*
invariant — a full count or a contiguous id range. Sorting alone is NOT enough (a record
deleted from the middle leaves the list sorted).
```python
from beliefgate import verify_coverage, CoverageClaim, CoverageKind, SourceFacts

facts = SourceFacts(
    present_count = len(rows),
    keys          = [r.id for r in rows],
    sorted_desc   = True,
    boundary_crossed = min(r.amount for r in rows) <= 10_000,  # we saw below the cutoff
    predicate_evaluable = True,
)
# the source SYSTEM claims this quarter had 1,204 qualifying records:
res = verify_coverage(CoverageClaim(CoverageKind.FULL_COUNT, total=1204), facts)
if res.ok:
    total = sum(r.amount for r in rows)     # provably the whole qualifying set
else:
    abstain()                               # you only have a page; go fetch the rest
```
**Payoff.** The system refuses to certify "I summed everything over $10k" unless it can
*prove* nothing qualifying was left out. It catches the silent partial-page total.

---

## Scenario 5 — An agent's cached number goes stale (bookkeeping memory)

**Setting.** A long-running ops agent computed *"current headcount = 4,312"* from the HR
table at the start of the session and remembered it. Forty minutes later, after two hires
and a departure, the user asks a question that reuses that figure.

**Without the gate.** The agent confidently reuses `4,312`. It's now wrong by 1, and the
agent has no way to know its own memory went stale. (In a 2,000-trial demo, a naive cache
served stale values **~60%** of the time when the source could change.)

**With the gate (bookkeeping memory).**
```python
from beliefgate import remember, recall

memo = remember(4312, {e.id: e.status for e in hr_rows}, label="headcount")
# ... time passes; the agent revisits the figure ...
value, memo, res = recall(memo, {e.id: e.status for e in current_hr_rows},
                          recompute=lambda rows: sum(s == "active" for s in rows.values()))
#  res.ok        -> source unchanged; value is the trusted 4312
#  res not ok    -> res.detail names the added/removed/changed ids; value is RE-DERIVED
```
**Payoff.** The agent never serves a derived number whose source moved under it. It either
proves the figure is still current or recomputes it — and tells you exactly what changed.

---

## When NOT to use it (so you don't force it)

- **Single-fact extractive lookup** ("what is cell X?") with an abstention option — we
  measured this: modern models, even cheap ones, abstain correctly and don't confabulate
  (0/40). Adding a gate here is latency for no gain.
- **Open/semantic QA** ("what does this contract *mean*?") — relevance isn't enumerable
  from the task; the gate has no anchor. Use an LLM; at most wrap it.
- **When `present` must be read from messy prose by an LLM** — then the *extractor* is the
  floor, not the gate. Feed `present` from a parser / DB / API.

---

## The one mental model

> Put the gate **before** an expensive or irreversible step that operates on a *known set*
> or a *derived value*: a total, a reconciliation, a percentile, a payment, a cached fact.
> It answers one question deterministically — "do I actually have all of it / is it still
> current?" — and it errs only toward honest refusal, never toward a confident wrong answer.

The LLM still does the language and the judgment. The gate just makes sure the LLM never
*computes or commits* on data that's silently incomplete — which is precisely where, as we
measured, confident models go confidently wrong.
