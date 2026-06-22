# In-Run Verification as a Decorrelated Residual: What a Cheap Check Can and Cannot Catch in Recursive LLM Systems

*A consolidated research report. Treat as a preprint / technical report, not a peer-reviewed
paper — see §9 (Limitations) and the honest scope notes throughout.*

---

## Abstract

A modern LLM is a frozen inference core; the intelligence of a *system* built around it lives
in the external harness that rebuilds context recursively, where one stage's output configures
the next. Such systems fail in a characteristic way: a cheap, local signal (a fast draft, a
memorized template, a plausible-but-ungrounded number) overrides the standing, correct one, and
the error propagates. The standard defenses — verify, deliberate, re-inject — are *antidotes*;
the open problem is the *diagnosis*: a cheap, in-run signal for **when** to fire them.

We give a unifying account: an in-run error detector is a **decorrelated residual** between two
estimators, and it works exactly to the degree the second estimator's failures decorrelate from
the fast path. We support this with (i) a measured **dose-response** — detection rate scales
monotonically with decorrelation (re-sampling 22% → surface-paraphrase 44% → execution 100%),
and the axis *terminates at program execution*, unifying detection with grounding; (ii) a
public-benchmark study (FinQA) where a deterministic grounding gate is provably leak-proof yet,
at scale against a calibrated baseline, **buys safety, not honesty-over-baseline**; and (iii) a
characterization of the **one wall** every cheap residual hits — a *systematic, confident error
is correlated across every cheap view*, leaving no residual — observed at three scales
(re-sample, cross-task, intra-network). We report two strong negatives: the cleanest fixation
phenomenon is confined to a narrow model band, and the white-box channel that might attack the
wall has no cheap substrate that both exhibits the phenomenon and exposes activations. The
contribution is a lens and its boundary, plus a shipped artifact (belief-gate), not a new
state-of-the-art method.

---

## 1. Introduction

### 1.1 The setting
An LLM call is stateless and deliberate. A single chain-of-thought answer is relatively safe
precisely because it is monolithic and self-contained. The moment one builds an architecture
*around* the core — a router, a cache, a fast draft, a multi-stage harness — cheap shortcut
paths are introduced, and the recursion acquires a new failure class: **recursive state gets
mistaken for proof**. Artifacts that can call the model again are no longer outputs; they become
state surfaces, and the task is "negotiated into a ditch."

### 1.2 Antidotes vs. diagnosis
We decompose the defenses into three **anti-runaway primitives**, each a way of refusing to let
the loop trust its own cheap output:
- **Grounding** — verify the state against its source before trusting it.
- **Restraint** — don't trust the fast path on novelty; deliberate or verify.
- **Anchoring** — hold the objective/identity invariant across the reconstruction.

Each is an *antidote*. The hard, open question — raised by a skeptic early in this work — is the
*sensor*: a cheap, in-run signal that tells you **where** the cheap path is about to fail, so you
fire the (expensive) antidote selectively rather than everywhere. This report is mostly about
that sensor: what shape it has, how far it goes, and the wall it hits.

### 1.3 Contributions
1. **A unifying account** (§2): an in-run detector is a *decorrelated residual* between two
   estimators; its catch scales with decorrelation and its cost is false-alarm.
2. **Grounding at scale, honestly** (§3): on FinQA, a deterministic grounding gate is leak-proof
   by construction, yet against a calibrated `direct` baseline it does not improve honesty — it
   makes *execution* safe. We report this deflation of our own earlier toy result.
3. **A dose-response** (§4): detection scales monotonically with decorrelation, the axis
   terminates at execution (so detection and grounding are one continuum), and we give a cost
   criterion for when a cheap sensor beats always-deliberating.
4. **The wall** (§5): a systematic, confident error is correlated across every cheap view and
   leaves no residual; we observe this at three scales and report the white-box channel's death
   for lack of substrate.
5. **Two supporting primitives** (§6): restraint (fixation) and anchoring (drift), measured.
6. **A shipped artifact**: belief-gate, a zero-dependency library + MCP server + agent skill.

We are deliberate about negatives and scope; §9 is a frank limitations section.

---

## 2. The decorrelated-residual account

**Claim.** An in-run detector compares the fast path's output to a second estimator and flags
disagreement (the *residual*). The residual is informative only when the second estimator's
*failures* are decorrelated from the fast path's. If the second estimator shares the fast path's
systematic error, they agree on the wrong answer and the residual is zero.

This single principle organizes every detector, working and failed:

| detector | second estimator | decorrelation | outcome |
| :--- | :--- | :--- | :--- |
| confidence | the path reporting on itself | none | blind on confident error |
| self-consistency | same model, re-sampled | ~none (stable error survives the vote) | weak |
| surface-paraphrase | same model, new surface | partial | partial |
| different-abstraction | same model, emit a formula → execute | high (removes the arithmetic channel) | strong |
| **grounding (belief-gate)** | **executed code** (set difference) | **maximal** (code shares nothing with the LLM template) | **leak-proof** |

Two consequences frame the rest of the paper:
- **Sensor ≠ corrector.** Decorrelation buys a *trigger* (they disagree), not the *answer*. The
  corrector is the antidote the trigger fires; the second estimator need not be authoritative,
  only decorrelated. Its fallibility surfaces as **false-alarm**, not as a wrong final answer.
- **The axis has a terminus.** Maximal decorrelation is *execution* — code that recomputes
  rather than re-prompts. So "the best cheap detector" and "the grounding primitive" are the
  same object at the same end of one axis.

---

## 3. Grounding at scale (and the honest deflation)

### 3.1 The toy result
A deterministic completeness check beats an LLM judging its own completeness. An LLM asked "is
this context complete for the task?" false-passes subtle interior gaps — **7/15** (a strong
model), **2/15** (a mid model). Moving the same check into executed code (set difference over a
question-derived required set) drops that to **0/15** for both. The library is leak-proof:
29/29 unit tests; 9,580 exhaustive decisions, 0 errors. End-to-end (LLM → gate → REPL) on
computable QA, the system answers exactly or abstains — **80/80 correct, 80/80 abstain** — while
the same models answering directly score **3–6/80** on the arithmetic. This is a clean double
dissociation: the gate fixes calibration (abstention), the REPL fixes arithmetic.

### 3.2 The scale test (FinQA)
We scaled to FinQA (a public financial-QA benchmark) to test the grounding claim with real
documents, gold arithmetic programs, and **annotated supporting evidence** (`gold_inds`), which
lets us build a *principled* insufficient-context condition by ablating the gold supporting row.

Deterministic core (offline, no model): on **548** valid items, our executor reproduces the gold
answer **98.7%** of the time, and the operand-grounding gate is **548/548 leak-proof** — it
answers when every operand is present and abstains on every gold-row ablation.

Arms: `direct`, `cot`, `selfcons`, `pal_repl` (PAL — emit a program, execute it), and
`gate_repl` (PAL + a deterministic operand-grounding gate that abstains if any operand is absent
from the context). Conditions: *sufficient* vs *ablated*. Macro-average across 5 models
(credit-stable runs):

| arm | confab (ablated) ↓ | precision | accuracy | coverage |
| :--- | :--- | :--- | :--- | :--- |
| direct | **16.6** | 77.4 | 67.5 | 86.8 |
| cot | 19.8 | 79.0 | 67.9 | 86.0 |
| selfcons | 23.2 | 75.6 | 63.7 | 84.1 |
| pal_repl | 31.2 | 78.9 | 71.9 | 91.4 |
| gate_repl | 24.7 | **80.7** | **72.3** | 89.3 |

### 3.3 The honest deflation
The dramatic toy result **did not replicate against a calibrated `direct` baseline**. The gate's
confabulation (24.7%) is *worse* than `direct` (16.6%): a calibrated model already self-abstains
when evidence is missing, so the gate's guarantee — *no answer computed from an absent number* —
catches a failure (fabrication) the model rarely commits. Its residual confabulation is mostly
**misselection** (a present-but-wrong number), which the value gate cannot catch by design.

What survives is narrower and defensible: **execution buys accuracy** (pal/gate ≈ 72% vs
direct/cot ≈ 67%), and **the gate makes execution safe** — PAL alone confabulates *more* (31%,
emitting a program over-commits the model), and the gate recovers that lost calibration (31 →
25) while giving the best precision (80.7), at zero extra inference cost.

> **Claim that holds:** the operand-grounding gate is how you make an accuracy-boosting execution
> path honest; it is *not* a way to make a model more honest than asking it directly.

### 3.4 A partial misselection sensor
To attack the residual (misselection), we added a second decorrelated estimator: **locate** the
question-relevant rows independently of the **compute** step, and abstain if an operand does not
come from a located row. On FinQA (n=60), this is the first thing to push confabulation *below*
the value gate (30% → 23%), catching 4 misselections for 2 correct answers lost — but only **4 of
18**. The rest slip through because compute and locate **agree on the wrong row** (a consistent
misread → zero residual). A partial fix, limited by exactly the wall of §5.

---

## 4. The dose-response

If the account in §2 is right, detection rate should rise monotonically with decorrelation. We
test this on rate-twist items (garden-path arithmetic that elicits template-capture). We
pre-register the decorrelation order (a mechanistic argument, *not* inferred from the result) and
report both catch and false-alarm.

| estimator | how it differs from the fast path | catch | false-alarm |
| :--- | :--- | :--- | :--- |
| self-consistency | nothing (re-sampled) | 22% | 12% |
| paraphrase | surface only | 44% | 38% |
| **expr** | output abstraction (emit a formula, code computes) | **100%** | 38% |
| cot | process (System 2) | ~100% | 0% |

Catch climbs **22 → 44 → 100** with decorrelation, confirming the principle. The winner, `expr`
— emit a formula, evaluate it in code — *is PAL/REPL*, confirming the axis terminates at
execution (§2). False-alarm is the cost (the decorrelated estimator is itself fallible). Two
mitigations, both measured: an **AND-ensemble** `expr & cot` reaches catch ≈ 100% with **0%**
false-alarm (the two estimators' false-alarms decorrelate) — but the best combo needs the
expensive `cot`; and a cheap **stability filter** (flag only if `expr` is unanimous across
samples) removes ~75% of false-alarms, leaving a residual of *confidently-wrong* formulas (§5).

**Cost criterion.** Modeling per-item cost (never / always / sensor-gated deliberation) with
`r = error-cost / deliberation-cost`, a cheap sensor (`expr`) becomes the optimal strategy only
when **r ≳ 2** (an error costs ≥ ~2× a deliberation) at moderate fixation. Below that, eating
errors is cheaper. This explains why the rate-twist substrate cannot show deployment value
(deliberation is cheap there) and where a cheap sensor *does* pay: **high-stakes chains**.

---

## 5. The wall

The strong result of this work is not any sensor's win; it is the **invariant** that bounds all
of them.

> A cheap residual is only as good as the decorrelation it can build, and a **systematic,
> confident error is correlated across every cheap view** — so it leaves no residual.

We observe the same wall at three scales:
- **Re-sample** — `expr`'s stability filter leaves ~25% *confidently-wrong* false-alarms (the
  model emits the *same* wrong formula repeatedly). *Measured.*
- **Cross-task** — the FinQA misselection sensor misses 14/18 because compute and locate share
  the misread. *Measured.*
- **Intra-network** — a white-box conflict probe would be blind on confident fixation (one
  circuit dominating ⇒ no co-active conflict ⇒ no signal). *Predicted.*

**The white-box channel is dead for lack of substrate.** A logit-lens probe (is the correct-token
*present-but-suppressed* in mid-layers of a confidently-fixated forward pass?) requires a model
that both *exhibits* fixation and *exposes* activations. We find these are **mutually exclusive
in cheap models**: the cleanest fixator (gemini-2.5-flash, ~38%) is closed; open local models
that expose activations do *not* fixate (Qwen2.5-1.5B: fast-mode TRAP 1/8 = noise, OTHER 7/8 =
scattered wrong answers, and it fails even the saturated canonical CRT — *incompetence, not
immunity*); the one open model that fixates is too large to be a local probe target. So the
white-box channel cannot even reach the field, and is predicted to hit the same wall if it
could.

The wall *is* breakable — the AND-ensemble shows catch ≈ 100% / 0% FA — but only by paying the
expensive estimator, which defeats the purpose of a *cheap* sensor.

---

## 6. The two supporting primitives

**Restraint (fixation).** Classic CRT does not fool modern models (**0/360** — the answer is
saturated into the weights); fixation requires *novel* garden-path structure. There it is
textbook System-1 template-capture: present in fast mode, **erased by chain-of-thought in every
model (0/80)**, with magnitude **model-specific** (the cleanest fixator gemini-2.5; gpt-oss and
deepseek immune). In a recursive loop, one stage-1 fixation poisons **38%** of chains
(propagated faithfully to a confidently-wrong final answer), and **one gate placed at the
fixation point rescues 100%** (62% → 100%). The architectural rule: place the anchor where the
cheap path is unreliable — not everywhere.

**Anchoring (drift).** A *salient* constraint (a required format tag) is held **100%** regardless;
a *soft* constraint (a persona identity) drifts specifically on pressure turns — **73%** retained
— and per-turn re-injection holds it at **100%**, *identically in two models*. The drift is
pressure-triggered, not gradual decay.

Both reduce to the same shape as grounding: a cheap signal (memorized template; a local "answer
in one word" instruction) overrides the standing/correct one unless an external anchor
(deliberate; re-inject) is engaged.

---

## 7. Discussion: the agency framing

Across the three primitives, what we engineered is the **regulatory layer** — the *governor* —
not agency. A raw LLM is all engine (it generates) and no governor (it has no set-point, does
not know when it is wrong, drifts under pressure). The three primitives are the governor's
*actuators* (verify, deliberate, re-inject). What is missing to make a self-regulating agent is
the governor's *sensor* — and this work's central finding is that the cheap, general sensor hits
a principled wall. So the honest map is: engine ✓, actuator ✓, sensor = resolved where the
antidote is free (grounding via set-difference, anchoring via re-injection), and a *named wall*
where it is not (restraint's confident-fixation case). We did not engineer the will; we
engineered the judgment, and we mapped exactly where the judgment's cheap sensor stops.

---

## 8. Related work (positioning)

The decorrelated-residual lens is adjacent to, and unifies, several lines: **self-consistency**
(majority over sampled chains — our account explains *why* it fails on systematic error: it
re-samples the same process), **selective prediction / abstention** (coverage–risk trade-offs —
we give a cost criterion and a deterministic abstention signal), **program-aided LMs** (execution
for arithmetic — we show it is the maximal-decorrelation point of a single detection axis),
**verifier models and self-correction** (consistent with the finding that LLMs cannot reliably
self-correct reasoning — our gate-vs-judge result is the deterministic complement), and
**OOD/novelty detection** (the open-form, novel-failure case is exactly OOD detection, a known
hard problem). The novelty here is the *unification* and the *boundary characterization*, not a
new method; positioning against these literatures with matched baselines is required before any
peer-reviewed claim (see §9).

---

## 9. Limitations (read this before citing)

- **Small n throughout.** Dose-response n=24 (9 captured); FinQA cells n=60–150; anchoring n=8
  dialogues. Results are *directional*; the load-bearing claims are the clean, repeated contrasts
  (gate 0/15; CoT 0/80; the 22→44→100 ordering; the cross-model confab pattern), not the precise
  rates.
- **The fixation phenomenon is model-locked.** The dose-response centerpiece rests largely on one
  model (gemini-2.5), because cheap models are either too weak (noise) or too robust (immune).
  This is a real external-validity weakness, honestly reported, and it is what kills the
  white-box arm.
- **The decorrelation account is a synthesis, not a new method.** Its components are adjacent to
  known work (§8); the contribution is the lens, the dose-response, and the wall — conceptual and
  diagnostic, not a SOTA result.
- **No matched baselines from the selective-prediction literature.** A peer-reviewed version would
  need to compare against established abstention/calibration methods on a shared benchmark.
- **One substrate per claim, mostly.** The cross-substrate framing (these are the same primitives
  in control loops and brains) is an analogy, not formalized.
- **Data hygiene caveat.** Early API runs were corrupted by credit/throttle outages (empty
  responses silently written); all reported numbers are from runs that passed an integrity check
  (>20%-empty files excluded), and the freshest credit-stable runs reproduce the patterns.

---

## 10. Conclusion

A recursive frozen-core system fails when a cheap, local signal overrides the standing, correct
one; the antidotes (verify, deliberate, re-inject) are known, and the open problem is the cheap
in-run sensor for *when* to fire them. We have shown that such a sensor is a **decorrelated
residual** between two estimators: its detection rate scales with decorrelation (measured 22 →
44 → 100), the axis *terminates at execution* (unifying detection with grounding), and its cost
is false-alarm with a clear break-even criterion. We have shown, against our own earlier toy
result, that at public-benchmark scale a leak-proof grounding gate buys *safety, not
honesty-over-baseline* — it makes execution safe rather than beating a calibrated model's native
abstention. And we have characterized the one wall every cheap residual hits: a *systematic,
confident error is correlated across every cheap view*, observed at three scales, with the
white-box channel that might attack it left without a cheap substrate that both fixates and
exposes its activations.

The contribution is a lens and its boundary — and a shipped artifact (belief-gate). The cure was
never the hard part; the diagnosis is, and we have drawn its limit precisely.

---

*Artifacts: `beliefgate/` (library, MCP server, agent skill); `bench/finqa/`, `bench/incubation/`,
`bench/anchoring/` (harnesses). Companion docs: DETECTOR.md, FINQA.md, MYTHOS.md,
INCUBATION_FIXATION.md, GATE_REPL.md, OVERVIEW.md.*
