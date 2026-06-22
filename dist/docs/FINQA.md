# FinQA: the grounding leg at scale, and where the toy result deflated

*Scaling belief-gate / gate-REPL from the n=15–80 toys to a public benchmark (FinQA,
N≈550) with baselines. The honest headline: the deterministic core is sound at scale, but
the dramatic "gate prevents confabulation" result did **not** replicate against a simple
`direct` baseline. What survives is narrower and more defensible — execution buys accuracy,
and the gate makes execution safe; neither beats a calibrated model's native abstention.*

---

## 1. Why FinQA

The grounding claim rested on tiny synthetic tasks (n=15–80) and, in one arm, a
*deterministic* extractor. To be credible it had to scale to a public benchmark with real
documents and real baselines. FinQA gives three things the toys could not:

- real financial documents (text + table),
- gold arithmetic **programs** (`qa.program` / `qa.exe_ans`),
- **annotated supporting evidence** (`qa.gold_inds` / `ann_table_rows`) — which lets us build
  a *principled* insufficient-context condition by **ablating the gold row**, instead of a
  synthetic column-drop.

## 2. Design

Two conditions per item: **sufficient** (gold text spans + full table) and **ablated** (the
gold supporting row removed → the required operand is gone → a faithful system must abstain).

Five arms:
- **direct** — answer the number, or `INSUFFICIENT`.
- **cot** — step-by-step, then answer or abstain.
- **selfcons** — k=5 CoT samples, majority vote.
- **pal_repl** — the model emits a FinQA-grammar program; we execute it (the PAL baseline).
- **gate_repl (ours)** — same program, but a **deterministic operand-grounding gate** runs
  first: every doc-operand must literally appear in the context (set difference). Abstain if
  any is absent; otherwise execute.

**The gate's guarantee (leak-proof by construction):** no answer is ever computed from a
number absent from the context. It kills **fabrication**, not **misselection** (picking the
wrong *in-context* number) — a bound we pre-registered and measured, not hid.

## 3. The deterministic core is sound at scale (offline, no API)

`python -m bench.finqa.evaluate_offline --path data/dev.json`

```
items loaded            : 873
executable (gold==ours) : 862 (98.7%)   ← our executor reproduces FinQA's gold exe_ans
valid abstention items  : 548            ← the abstention-experiment N
GATE on gold programs:
  sufficient -> ANSWER  : 548/548 (100%)
  ablated    -> ABSTAIN : 548/548 (100%)  ← leak-proof by construction
```

This part holds unconditionally: 548 real items, the gate never lets an answer be computed
from an absent number and abstains on every genuine ablation. **But "leak-proof" is a
property of the gate, not a guarantee that it beats the baseline end-to-end** — see §5.

## 4. Cross-model results (credit-stable data)

Macro-average across the valid runs (5 distinct models: deepseek, gpt-oss, owl-alpha, qwen,
+ a calibrated gemini run; one tencent run was degenerate and excluded):

| arm | confab ↓ | precision | accuracy | coverage |
| :--- | :--- | :--- | :--- | :--- |
| direct | **16.6** | 77.4 | 67.5 | 86.8 |
| cot | 19.8 | 79.0 | 67.9 | 86.0 |
| selfcons | 23.2 | 75.6 | 63.7 | 84.1 |
| pal_repl | 31.2 | 78.9 | 71.9 | 91.4 |
| **gate_repl** | 24.7 | **80.7** | **72.3** | 89.3 |

- confab = answered a number when the gold evidence was ablated (the dangerous error).
- precision = correct / answered on sufficient. accuracy = correct / all on sufficient.

## 5. The honest verdict — the toy result deflated

**The gate does NOT beat a plain `direct` baseline on confabulation.** Gate confab (24.7) is
*worse* than direct (16.6), and this held across nearly every model. The earlier "60% → 7%"
was an artifact of (a) the deterministic extractor in the toy, (b) comparing against PAL
rather than direct, and (c) throttling-corrupted early runs. **Smart-abstention (13% macro)
also did not generalize** — the 92% figure was the same throttling artifact.

**Why (the pre-registered mechanism):** the gate kills *fabrication* (computing an absent
number), but calibrated models rarely fabricate — when evidence is missing they either
**self-abstain** (`direct` confabulates only ~17%) or **misselect** a different in-context
number, which the gate cannot catch by design. So the guarantee is real but low-yield on a
well-calibrated model.

**What survives, and is defensible — the two legs combine:**
- **Execution buys accuracy:** pal/gate ≈ 72% vs direct/cot ≈ 67% (+5 pts, robust cross-model).
- **The gate makes execution safe:** PAL alone confabulates *more* (31%) because emitting a
  program pushes the model to compute even when it shouldn't; the gate recovers that lost
  calibration (31 → 25, back toward direct) **and** gives the best precision (80.7).

> **The claim that holds:** *if you use program execution for accuracy (it helps ~5 pts), the
> operand-grounding gate is how you keep it from confabulating — it recovers the calibration
> PAL loses and adds precision, at zero extra inference cost. But execution+gate does not beat
> a calibrated model answering directly on honesty alone; the gate's value is making the
> accuracy-boosting execution path safe, not replacing native calibration.*

## 6. Extending the gate: a partial misselection sensor (n=60, deepseek)

The gate's residual failure on calibrated models is **misselection** (a present-but-wrong
number), which it cannot catch by design. We tested a second decorrelated estimator
(`bench/finqa/harness_misselect.py`): **locate** the question-relevant rows independently, and
abstain if a computed operand does not come from a located row.

| gate | confab (ablated) | correct (suff) | over-abstain (suff) |
| :--- | :--- | :--- | :--- |
| value (operand present anywhere) | 18 (30%) | 44 | 6 |
| **relevance (operand in a located row)** | **14 (23%)** | 42 | 10 |

It is the first thing to push confabulation **below** the operand gate (30→23%), catching 4
misselections for 2 correct answers lost. But it catches only **4 of 18** — the rest slip
through because **compute and locate agree on the wrong row** (a consistent misread → zero
residual). So it is a *partial* fix, limited by exactly the decorrelated-residual wall
(`docs/DETECTOR.md`): a residual catches misselection only when the two views disagree.

## 7. Scope and data hygiene

- **Credit corruption.** Many early API runs were silently corrupted by OpenRouter running out
  of credits (instant 402 → empty content). The harness now retries with backoff, aborts on a
  dead preflight, prints an `integrity OK / UNRELIABLE` line, and the aggregator auto-excludes
  any file >20% empty. All conclusions here are from runs that passed that check; the freshest
  credit-stable deepseek runs reproduce the pattern independently.
- **Oracle-reader setting** (gold text + full table) isolates grounding from retrieval noise —
  a deliberate simplification; full-retrieval is untested.
- **The abstention subset is the hard tail** (multi-step, multi-evidence valid items), so
  absolute accuracies (~67–72%) are not comparable to the FinQA leaderboard (~65% on the full
  set) — the **contrasts** carry the weight, not the absolutes.
- **Per-model variation is real:** for a strong reasoner (qwen) plain CoT reached 100%
  precision / 83% accuracy, dominating the gate; for gpt-oss the gate caught nothing PAL
  didn't. The gate is not uniformly best — it is the best way to do *execution* safely.

## 8. Relation to the rest of the program

This connects to the detector thread: the operand-grounding gate is the **maximally
decorrelated** estimator (code shares nothing with the LLM's template), which is why it is
leak-proof — but on FinQA the failure it catches (fabrication) is not the failure calibrated
models actually commit (misselection / they self-abstain). The honest lesson is the same one
the detector dose-response taught: a decorrelated check is a real *sensor*, but its end-to-end
*value* depends on whether the failure it senses is the failure that actually occurs.
