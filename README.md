# belief-gate / gate-REPL

Verify what an LLM has, instead of trusting what it says it has. This repo is an
empirical study and a small library for **completeness verification by execution,
not by judgment** — plus the honest map of where that discipline applies and where
it does not.

The core result: an LLM judging "is this context complete?" false-passes on subtle
gaps (7/15 on one model, 2/15 on another). Moving the check into executed code — the
LLM declares the *required* set, the CPU computes `required − present` — drops that
to **0/15, on both models**, and the system never certifies an answer it can't prove.

End-to-end, the payoff is a double dissociation: routed through **LLM → gate → REPL**, a
computable question is answered exactly or abstained — **80/80 correct, 80/80 abstain**
across two models — while the same models answering directly score **3–6/80** on the
arithmetic (gemini: 0/40) and confabulate on incomplete data. The gate fixes calibration;
the REPL fixes arithmetic; only the full pipeline is clean on both.


## FULL READ ME: https://github.com/JCOMAIA/gate-repl/tree/main/dist 


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


## DEMO
https://joaomaia.com.br/demo/
<img width="1093" height="869" alt="image" src="https://github.com/user-attachments/assets/ca14770a-d75b-473d-ab01-8f79623fa494" />
