# The detector frontier: a decorrelated residual, and where it hits the wall

*Can a cheap in-run signal tell you WHEN to fire the antidote (verify / deliberate)? This
is the open problem the whole anti-runaway program kept hitting. We measured it. The honest
answer: the sensor is a **decorrelated residual between two estimators**, it works to the
degree the second estimator's failures decorrelate from the fast path — and its practical
value is gated by **false-alarm**, which grows with the richness of the output space.*

---

## 1. The principle (the other-session convergence)

The sensor is a **residual between two estimators**. It only fires if the second estimator's
failures are *decorrelated* from the fast path. Every detector that failed earlier re-sampled
the **same** process and shared its systematic error → zero residual:
- **confidence** — the path reporting on itself → total correlation → blind on confident error.
- **self-consistency** — same model rerolled; a *stable* trap survives the vote.
- **paraphrase** — different surface → *partial* decorrelation → partial signal.
- **grounding (belief-gate)** — code shares *nothing* with the LLM's template → maximal
  decorrelation → leak-proof.

## 2. The dose-response confirms it (gemini-2.5-flash, rate-twist, n=24 / 9 captured)

CATCH rises with **pre-registered** decorrelation order (`bench/incubation/harness_doseresponse.py`):

| estimator | how it differs from the fast path | CATCH | FALSE-ALARM |
| :--- | :--- | :--- | :--- |
| selfcons | nothing (rerolled) | 22% | 12% |
| paraphrase | surface | 44% | 38% |
| **expr** | output abstraction (emit formula, code computes) | **100%** | 38% |
| cot | process (System 2) | ~100%* | 0% |

\*raw 78%, depressed by 2 null cot responses; among parsed cot, 7/7.

**`expr` = emit a formula, compute in code = PAL/REPL in disguise.** So the decorrelation axis
*terminates at execution* — the detector thread and belief-gate are the **same axis**:
`selfcons → paraphrase → expr/REPL → code-oracle`.

## 3. False-alarm is the wall — and it scales with the output space

The decorrelated estimator is itself fallible; its fallibility surfaces as false-alarm
(**sensor ≠ corrector**). Two ways to fight it, both measured:

- **AND-ensemble:** `expr & cot` → catch ~100%, FA **0%** (the FAs of the two estimators hit
  *different* items). But the best combo needs cot (the expensive antidote).
- **Stability filter (cheap, same model):** flag only if `expr` is unanimous across K samples.
  On owl-alpha, this filtered **6/8** false-alarms (the wrong formulas were unstable) — but **2
  survived** as *confidently-wrong* (same wrong formula 4×), the irreducible residual.

**FA grows with the richness of the answer space:** rate-twist `expr` FA 38%; FinQA value-
disagreement (`direct` vs `pal`) FA **59–71%** — because FinQA numbers have many valid forms
(scaling, formatting, paths), so estimators disagree on the *value* even when both are right.

## 4. The cost criterion (when is a sensor worth it at all)

Modeling per-item cost (never / always / sensor-gated deliberation) with `r = error-cost /
deliberation-cost`: a cheap sensor (`expr`) becomes the optimal strategy only when **r ≳ 2**
(an error costs ≥ ~2× a deliberation), at 20–30% fixation. Below that, just eat the errors.
This is why rate-twist can't show deployment value (cheap deliberation → low r) and where a
sensor *does* pay: **high-stakes chains** (one wrong step ≫ the cost of a check).

## 5. Two hard walls we hit honestly

- **The phenomenon is gemini-locked.** Rate-twist template-capture appears in gemini-2.5-flash
  (~38%) but **4 cheap models are immune** (owl-alpha 1/40, minimax 0/40, gpt-oss & deepseek
  earlier). Gemini is excluded on cost, so fixation-detection can't be cheaply replicated.
- **A decorrelated estimator must also be *competent*.** owl-alpha's `expr` was maximally
  decorrelated *and* garbage (wildly-scaled wrong formulas, unstable) → it added noise, not
  signal, and stability even killed the one real catch. Decorrelated **and** accurate, both.

## 6. The misselection sensor — a partial fix, same wall (FinQA, deepseek, n=60)

On *calibrated* models the failure is not fabrication (which grounding catches) but
**misselection** — a present-but-wrong number. We built a second decorrelated estimator
(`bench/finqa/harness_misselect.py`): **compute** (emit the program → operands) vs **locate**
(independently, which rows answer the question), and abstain if an operand is not in a located
row. Result vs the plain value gate:

| gate | confab (ablated) | correct (suff) | over-abstain (suff) |
| :--- | :--- | :--- | :--- |
| value (operand present anywhere) | 18 (30%) | 44 | 6 |
| **relevance (operand in a located row)** | **14 (23%)** | 42 | 10 |

It is **the first thing to push confabulation below the operand gate** (30→23%), catching 4
misselections for a cost of 2 correct answers lost — but only **4 of 18**. The other 14 slip
through because **compute and locate AGREE on the wrong row** (a consistent misread): when the
two views share the error, the residual is zero. The sensor catches the *decorrelated* subset
of misselection and misses the *correlated* one — the same wall, again.

## 7. The white-box channel: dead at the gate (Aura, gate #0)

The remaining hope was a white-box probe (logit-lens: is the correct-answer token
*present-but-suppressed* in mid-layers of a confidently-fixated forward pass?). It died at the
cheapest possible check, before any build:

- **The phenomenon and white-box access are mutually exclusive in cheap models.** Rate-twist
  fixation appears cleanly only in gemini-2.5 (**closed** — no activations). Open models that
  run locally and expose activations (Qwen2.5-1.5B, gpt-oss, deepseek) **do not fixate**. On
  Aura's Qwen-1.5B base, fast-mode TRAP = 1/8 (noise), OTHER = 7/8 (scattered wrong answers,
  not the template) — and it fails even the saturated canonical CRT (1/4). That is **not
  immunity, it is incompetence**: below the floor where fixation is well-defined.
- So fixation is a **mid-capability** phenomenon: too weak → noise; too robust/deliberate →
  immune; the band that fixates cleanly is narrow (gemini-class). The only open model that
  fixates (qwen3-235b) is too large to be a local probe target.

**Even if a substrate existed**, the probe was predicted to inherit the confidence blind spot:
confident fixation = one circuit dominating = no co-active conflict = no signal — the same
correlated-failure wall, intra-network. So the white-box is doubly blocked: *measured* dead
for lack of substrate, and *predicted* to hit the wall even if alive.

## 8. The one wall, at three scales (the result)

The strong scientific output of this thread is not any sensor's win — it is the **invariant**:

> A cheap residual is only as good as the decorrelation you can build, and a **systematic,
> confident error is correlated across every cheap view** — so it leaves no residual. The same
> structural requirement blocks the sensor at three scales:
> **re-sample** (expr-stability: ~25% confidently-wrong, irreducible) ·
> **cross-task** (FinQA compute-vs-locate: 14/18 misselections share the misread) ·
> **intra-network** (white-box: confident fixation = no conflict — *predicted*, no substrate).

Epistemic honesty: two of the three are **measured** (expr-stability, FinQA-locate); the
intra-network one is **predicted and substrate-blocked**, not measured. The black-box wall is
the proven core; the white-box is its predicted recurrence with no field to test it on.

**Joint verdict (both sessions, by data):** the cheap, general restraint sensor is not
crackable with available substrate — black-box hits the correlated-confident wall; white-box
has no model that both exhibits the phenomenon and exposes activations cheaply. The AND-ensemble
(`expr & cot` → 0 FA) shows the wall *is* breakable — but only with the expensive estimator,
which defeats the point of a cheap sensor.

---

*One line. A cheap in-run detector is a decorrelated residual; it works to the degree the
second estimator decorrelates from the fast path and is itself competent — and the one thing
it cannot crack, at any scale, is the systematic-confident error that is correlated across
every cheap view. That single wall, not any sensor's victory, is the result; and the white-box
channel that might have attacked it has no cheap substrate that both fixates and exposes its
activations.*
