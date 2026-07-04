# Belief-gate as a control layer over RAG: why it makes RAG better

*A measured report. Belief-gate is not a retrieval method and does not compete with
one. It is a **completeness control layer** that wraps any retriever. This report
shows — on a deterministic, reproducible test with a real text corpus and no API —
the three specific ways that layer improves a RAG pipeline, states precisely where
the improvement stops, and gives a 4-question checklist for whether YOUR RAG needs
it (most don't).*

---

## 0. The claim, made falsifiable

Loose version: *"belief-gate makes RAG better."* That is not testable until we say
**better at what, and by what mechanism.** This report commits to three concrete,
measurable claims and one hard boundary:

1. **It eliminates the dangerous error** — answering confidently while a required
   fact was never retrieved (false-complete).
2. **It recovers weak retrieval via gate-driven re-retrieval** ("recursion"): a poor
   retriever, wrapped, reaches the recall ceiling of a strong one.
3. **It does so cost-aware** — it escalates retrieval *only* on the queries that need
   it, not on every query.
4. **Boundary:** it is a *control layer*, not a retriever. With no RAG under it, it
   answers nothing, and it cannot raise the retriever's recall ceiling — it can only
   make the retriever *reach* that ceiling and tell the truth about the rest.

Everything below is the evidence for those four statements.

---

## 1. Why a control layer is even needed

A plain RAG pipeline has **no abstention path**. It retrieves top-k, hands the
context to the reader, and the reader answers — *whether or not the context actually
contains what the question requires*. When retrieval is incomplete (a required fact
sits below the cut, or is not in the corpus at all), the pipeline does not know it is
incomplete. It answers anyway. That confident-wrong answer over missing data is
**confabulation**, and it is the single failure mode RAG cannot self-detect, because
the missing evidence is, by definition, not in front of the reader to notice.

Belief-gate inserts exactly one decision before the answer: **is every enumerable
requirement actually present in what was retrieved?** — decided by executing a set
difference (`required − present`) in code, not by asking the model to judge
completeness. If the difference is empty, proceed. If not, the gap is named exactly,
and the pipeline either re-retrieves to close it or abstains with the missing list.

This only applies where the requirement is an **enumerable set** (a list of invoice
IDs, a set of months, N named entities). That is the regime this report measures; it
is not a claim about open-ended QA. See §6 for the checklist that decides fit.

---

## 2. The experiment (deterministic, no API, reproducible)

Code: [`bench/proto_rag_gate.py`](../bench/proto_rag_gate.py). Run:
`python -m bench.proto_rag_gate`.

We control ground truth so we can score exactly what each pipeline gets right and
wrong — no LLM judgment anywhere in the scoring.

- **Corpus:** real repository text chunked into **779 chunks** (`rlm.txt`, `COT.txt`,
  `LIFEHARNESS.txt`, `MemCollab.txt`, `ARLMCOT.txt`, `InsightMemoria.txt`).
- **Facts:** 16 distinct facts, each planted into a distinct real chunk with a unique
  topic token — **except 4 facts that are never planted** (absent from the corpus, so
  retrieval can *never* find them: the unrecoverable stress case).
- **Queries:** 60 queries, each requiring an enumerable set of 3 facts. Result:
  **28/60 fully recoverable** (all 3 facts exist somewhere), **32/60 unrecoverable**
  (at least one required fact is absent from the corpus).
- **Retrievers (real, no deps):** `bm25`, `tfidf` (cosine), and `brute` (retrieve the
  *entire* corpus = perfect recall — the strongest possible baseline).
- **Pipelines:** `RAG_plain` (top-k, answer), `RAG_gate` (top-k → gate → escalate
  `k → 2k → 4k → all` until complete, else abstain), and `GATE_only` (the gate with
  **no retriever** feeding it — the control that tests "can the gate replace RAG").

Scoring: an answer is **CORRECT** iff every required fact was actually in the
retrieved context; **FALSE_COMPLETE** iff the pipeline answered while a required fact
was missing (the dangerous error); **ABSTAIN** iff it declined with the exact gap.

---

## 3. Results

```
pipeline   retr     CORRECT  FALSE_COMPLETE  ABSTAIN   chunks_pulled
RAG_plain  bm25           2              58        0            600
RAG_plain  tfidf         28              32        0            600
RAG_plain  brute         28              32        0         46,740
RAG_gate   bm25          28               0       32         25,608
RAG_gate   tfidf         28               0       32         25,208
RAG_gate   brute         28               0       32         46,740
GATE_only  -              0               0       60              0
```

(28/60 recoverable, 32/60 unrecoverable. `top_k = 10`.)

---

## 4. What the numbers show — the three improvements

### 4.1 It eliminates the dangerous error (false-complete → 0)

Every `RAG_plain` row carries a large **FALSE_COMPLETE** count: it answers confidently
on queries where a required fact was never retrieved. Even `brute` — *perfect recall,
the whole corpus in context* — still false-completes **32/60**, because 32 queries
need a fact that is **absent from the corpus entirely**. No amount of retrieval fixes
that; the reader simply cannot know the fact is missing.

Every `RAG_gate` row has **FALSE_COMPLETE = 0**. The gate converts each of those
confident-wrong answers into either a correct answer (when re-retrieval finds the
fact) or an honest abstention with the exact missing list (when the fact is truly
absent). **This is the primary, unconditional win: the pipeline stops lying about
completeness.** It is also the one improvement a stronger retriever cannot buy —
`brute`'s perfect recall does not remove a single false-complete; the gate removes
all of them.

### 4.2 It recovers weak retrieval via re-retrieval — the "recursion"

Look at `bm25`. On its own it is a poor retriever here: **2/60 correct**. Wrapped in
the gate, the same `bm25` reaches **28/60** — *identical to `brute`'s perfect-recall
ceiling.* The gate did not improve the retriever; it **drove the retriever to run
again, deeper, until the required set was covered.** That escalation loop
(`k → 2k → 4k → all`) is exactly the "recursion" that turns a weak retrieval method
into a strong-recall pipeline. The control layer makes the *choice of retriever
matter less*, because it keeps pulling until the requirement is met or provably
cannot be.

### 4.3 It does this cost-aware — escalation only where needed

The naive way to get `brute`-level recall is to always retrieve everything: `brute`
pulls **46,740** chunks across the run. Gate-wrapped `bm25` reaches the *same
accuracy* while pulling **25,608** — roughly **45% less retrieval work** — because it
escalates *only on the queries the gate flags as incomplete* and stops the moment the
requirement is covered. The gate is not just a safety net; it is a **budget
allocator**: full retrieval effort spent precisely where completeness demands it,
top-k elsewhere.

---

## 5. The boundary — control layer, not replacement

The same table refutes the stronger claim that the gate is "superior to RAG" or could
*be* RAG:

- **`GATE_only`: 0 correct, 60 abstain.** With no retriever feeding it, the gate's
  `present` set is always empty, so every requirement is "incomplete" and it answers
  nothing. The gate produces zero information on its own — it is entirely parasitic on
  a retriever for the content it verifies.
- **It cannot raise the recall ceiling — only reach it.** This is the one line most
  easily misread as a contradiction, so precisely: there are two different "recalls."
  The **ceiling** is what the retriever *could* find if it pulled the whole corpus —
  here, the **28** recoverable queries (the other 32 need facts that simply are not in
  the corpus). The **delivered** recall is what a fixed `top_k` actually returns —
  `bm25` at top-10 delivers only **2**. The gate does **not** move the ceiling from 28
  (it cannot invent a document that isn't there). What it does is close the gap between
  *delivered* (2) and *ceiling* (28), by re-retrieving until the required set is
  covered — and tell the truth on the 32 that no retriever can reach.

  > Analogy: a student who reads only the first 10 pages and answers everything. The
  > answer is on page 200 — the library *has* it (high ceiling), but he never turned
  > there (low delivered). The gate is the teacher who says "you're missing fact X,
  > keep looking" until he finds it or the library genuinely lacks it. The teacher
  > adds no books (cannot exceed the ceiling) but forces full use of the library and
  > an honest "we don't have it" for the rest.

  So "makes RAG better" and "cannot exceed the recall RAG can achieve" are both true
  and are about different things: the first is *reaching the ceiling and being honest*
  (`2 correct + 58 lies → 28 correct + 0 lies`); the second is *not moving the ceiling*
  (never past 28).

So the precise, defensible statement is:

> Belief-gate is a **completeness control layer** that measurably improves any RAG
> pipeline — it drives false-complete to zero, lifts weak retrievers to the strong
> retriever's recall ceiling via re-retrieval, and spends retrieval budget only where
> needed. It is **not** a retriever, does **not** replace RAG, and cannot exceed the
> recall the underlying RAG can achieve. It controls RAG; it is not RAG.

---

## 6. Should YOU put a gate on your RAG? — the 4-question checklist

**No, not on every RAG.** The gate fits a specific *shape* of problem, and most RAGs
don't have that shape. Add it **only when all four are true**:

| # | question | why it matters |
| :-- | :--- | :--- |
| 1 | **Is the requirement an enumerable set you know in advance?** (a list of IDs, months, entities, checklist items) | If you can't name the keys, `required − present` is undefined. This is the hard gate. |
| 2 | **Does a silently missing item become a confident, wrong answer?** (failure mode = *fabrication*, not *misselection*) | The gate catches an *absent* required item. It does **not** catch a *present-but-wrong* one. |
| 3 | **Does a wrong answer cost more than abstaining / re-retrieving?** (money, legal, compliance, safety) | The gate trades some over-abstention for zero confabulation. Worth it only when confabulation is expensive. |
| 4 | **Is the base reader poorly calibrated to abstain on its own?** | If the model already says "I don't have that", the gate adds latency, not honesty. This is the FinQA deflation (§7). |

Fail any one → **don't add it.** It becomes friction (extra extraction call,
over-abstention) with no gain.

**Where all four typically hold (real, everyday):**

- **Accounting / finance** — "reconcile all N invoices in this batch"; required = the
  declared IDs. A missing one silently corrupts the total.
- **Payroll** — are all employees of the department in the export before totalling?
- **Fixed-coverage reports** — a close that must cover all 12 months / all regions;
  the query silently dropped one → sum of 11, reported confidently.
- **Legal (existence only)** — a filing must address a fixed list of exhibits/claims;
  did the retrieved context surface all of them? (existence, not merit — the boundary.)
- **Compliance / audit** — SOC2, ISO, regulatory checklist: does the report cover all
  K required controls? The requirement *is* the checklist.
- **BOM / procurement** — do all parts in the bill of materials appear in the quote?
- **KYC / onboarding** — are all mandatory documents present before approval?
- **Lab / medical panels** — are all N required results in before interpreting?

**Where it does NOT fit (most RAGs):** open QA ("what does the contract say about
X?"), summarization, semantic search, chat over documents — no enumerable required
set; and any case where the danger is a *wrong-but-present* answer (misselection),
which the gate does not catch.

> One line: it's a seat belt. You don't bolt it onto an office chair — you put it
> where a collision is expensive. Enumerable requirement + high stakes + a reader that
> won't abstain on its own → yes, always. Everything else → no.

---

## 7. Honest bounds (do not over-read this)

- **This isolates the *retrieval-completeness* layer, not end-to-end honesty.** The
  test models `RAG_plain` as *always* answering when context is incomplete (no native
  abstention). Real LLM readers sometimes abstain on their own. When they do, the
  gate's honesty edge shrinks — this is not hypothetical: at scale on FinQA, against a
  *calibrated* direct baseline, the gate did **not** beat the model's native
  calibration on confabulation (see [FINQA.md](FINQA.md)). The false-complete
  reductions here (e.g. 58 → 0) are the **structural upper bound**, larger than what a
  well-calibrated reader would leave on the table. This is exactly why checklist
  question #4 exists.
- **The win is real but scoped to the enumerable-required-set regime.** Where the
  requirement is not an enumerable set (open QA, summarization, free interpretation),
  `required − present` is undefined and this layer does not apply. See
  [SCENARIOS.md](SCENARIOS.md) for the measured boundaries.
- **The guarantee is conditional on the `present` extraction.** The gate computes on
  the `present` set it is handed. If that extraction is wrong (the reader mis-reports
  what it sees), the gate faithfully computes on wrong input. It catches *fabrication*
  (absent item claimed present), not *misselection* (present item that is wrong).
- **Retriever quality still matters for cost.** The gate lifts `bm25` to `brute`'s
  *accuracy*, but a better base retriever reaches completeness with less escalation
  (fewer re-retrieval rounds). The gate reduces the *penalty* for a weak retriever; it
  does not make retriever choice free.
- **n is one deterministic run.** The mechanism is deterministic (set difference), so
  the *structure* of the result is stable, but the specific counts depend on corpus,
  seed, `N_ABSENT`, and `top_k`. All are parameters at the top of the harness — change
  them and re-run.

---

## 8. One line

Belief-gate makes RAG better in three measurable ways — it kills confident-wrong
answers over missing data, it lifts a weak retriever to a strong retriever's recall by
re-retrieving until the required set is covered, and it spends that extra retrieval
only where completeness demands it — while never becoming a retriever itself: with no
RAG beneath it, it answers nothing, and it can never exceed the recall RAG provides.
It is the control layer over RAG, not a replacement for it — and it belongs only on
the RAGs whose requirement is enumerable, whose stakes are high, and whose reader
won't abstain on its own.
