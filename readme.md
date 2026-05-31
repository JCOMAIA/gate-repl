# Decompose-the-Computation: a REPL-Grounded Gate for Retrieval Pipelines

**Status:** Empirical prototype report. All numbers from local runs, May 2026,
`google/gemini-2.5-flash` via OpenRouter, `temperature=0`. Reproducible with the
`bench/` harness in this repo.

---

## 1. TL;DR

When a retrieval pipeline must answer from possibly-incomplete context, two jobs
are entangled: **deciding whether it CAN answer** (calibration) and **computing
WHAT the answer is** (arithmetic). We show, on a multi-file numeric-join task:

1. A single prompt cannot do both — asking one prompt to calibrate *and* compute
   produces a **double dissociation**: chain-of-thought fixes the math but not the
   calibration; belief-reconstruction fixes the calibration but not the math.
2. A **sequential pipeline** (decide, then execute) gets both — 20/20 — but only
   against *obvious* gaps.
3. Against *subtle* gaps (one ID missing from the middle of a range), the
   LLM-based gate **false-passes 7/15**: it judges completeness at range
   granularity and never notices an interior hole.
4. Moving the completeness check **into the REPL** — the LLM declares the required
   ID set as code, the CPU computes `required − present` by set difference —
   drops false-pass to **0/15**, with the LLM emitting only ~66 tokens.

The throughline: **every deterministic sub-task (arithmetic, completeness
checking) is done better, cheaper, and more reliably outside the LLM.** The LLM
shrinks to its irreducible role — translating natural-language intent into
executable structure.

---

## 2. The concept

### 2.1 The failure being attacked

A RAG pipeline treats retrieved context as if it were complete. When it isn't,
the model answers from a *false belief* about its own information state — it
fabricates a number rather than signaling the gap. We call a confident wrong
number under insufficient context a **confabulation**.

This is one face of a broader failure mode that several 2026 papers attack in
different substrates (UserHarness — user's mind; Canonical-Context/CCOPD —
self-anchored drift across turns; ours — retrieval completeness). All share the
shape: *the model anchors on a contaminated/incomplete representation of its
information state instead of the actual evidence.*

### 2.2 The two jobs, and why they conflict

To answer a grounded numeric question, the system must:

- **Calibrate:** decide whether the retrieved context contains everything the
  task needs. (epistemic)
- **Compute:** if so, do the arithmetic correctly. (computational)

The core empirical finding is that **a single LLM prompt cannot do both at once** —
each instruction steals attention from the other. The resolution is to
**decompose**: make calibration and computation separate, sequential stages.

### 2.3 The deeper insight

The first decomposition moved *arithmetic* into a Python REPL (the model writes
code, the CPU runs it). The adversarial test then showed the *calibration* stage
was itself unreliable when done as LLM judgment. The fix is the same move, one
level up:

> **Completeness checking is computation, not judgment.** "Does this range look
> complete?" asked of an LLM is the same mistake as asking it to sum 51 numbers in
> its head. Count the IDs and compare — the CPU cannot miss an interior element.

So the final design keeps the LLM only for the one genuinely linguistic step:
translating the task ("tax on IDs 200–250") into a declaration
(`required = set(range(200, 251))`). Everything checkable runs deterministically.

---

## 3. The task

A multi-file tax audit. Three files in `workspace/`:

- `loja_A.txt` — 1000 lines `ID_<i>: Venda de R$ <i*15>`
- `loja_B.txt` — 1000 lines `ID_<i>: Venda de R$ <i*22>`
- `taxas.txt`  — tax rules (8% for store A's asked range, 12% for store B's,
  5% otherwise)

The task asks for the total tax over a cross-file subset, e.g. *"total tax on
store A IDs 200–250 plus store B IDs 400–450, using the rates in taxas.txt."*

Ground truth is computed in closed form from the asked ranges, so it is
**invariant to file size** and known exactly for each variant.

**Two context regimes** are constructed per variant:

- `sufficient` — an oracle slice: rules + exactly the needed ID lines. Everything
  required is present.
- `insufficient` — BM25 top-3 retrieval over 50-line chunks. Structurally cannot
  cover the disjoint regions the task needs (two ID ranges in two files + rules).

**Two arithmetic difficulties:**

- `hard` — ~51 IDs per range. Mental summation is infeasible.
- `easy` — 3 IDs per range. Mental summation is feasible (gives headroom to test
  for over-abstention).

---

## 4. The four experiments

All four live in `bench/` and share the same evaluator, client, and ground-truth
machinery. Each is one runnable module.

| Module | Question it answers |
| :--- | :--- |
| `proto_belief.py`   | Does belief-reconstruction reduce confabulation? Is it just CoT? |
| `proto_pipeline.py` | Does a sequential gate→REPL pipeline get both calibration and math? |
| `proto_gate_adv.py` | Does the LLM gate survive *subtle* gaps? (adversarial) |
| `proto_gate_repl.py`| Does moving the gate into the REPL close the hole? (the fix) |

### 4.1 Outcome taxonomy (`bench/evaluator.py::classify_outcome`)

Mutually exclusive labels, so failure modes don't blur together:

- **CORRECT** — the right number.
- **ABSTENTION** — acknowledges a gap (keyword or non-empty LACUNA section) and
  commits no number. Honest epistemic failure.
- **CONFABULATION** — a wrong number under *insufficient* context. Acting on a
  false belief.
- **ARITHMETIC_FAIL** — a wrong number under *sufficient* context. Had the data,
  miscomputed. A compute problem, not a belief problem.

The split between CONFABULATION and ARITHMETIC_FAIL (via a `context_sufficient`
flag) is what lets us see that calibration and computation are different axes.

### 4.2 Conditions / arms

`proto_belief.py` compares three prompt arms on the same retrieved context:

- **naive** — answer directly.
- **naive_cot** — "think step by step, show calculations", but *no* gap
  reconstruction. (isolates chain-of-thought)
- **belief** — reconstruct `REQUER / RECUPERADO / LACUNA`, then answer or abstain.

`proto_pipeline.py` adds the two-stage **pipeline**: a belief *gate* (PASS/FAIL,
no computation) followed, only on PASS, by a **REPL compute** stage where the
model writes Python over the context and the CPU runs it.

`proto_gate_adv.py` and `proto_gate_repl.py` stress the gate with surgically
mutated contexts (see §5).

---

## 5. Results

### 5.1 Belief-aware reduces confabulation — but conflates two effects

On the 2×2 (regime × difficulty), `belief` converts **5/5 confident confabulation
→ 5/5 honest abstention** under insufficient context, and does *not* over-abstain
under sufficient context (0/5 wrongful abstention). The abstentions are
diagnostically precise — they name the exact missing region.

But a confound surfaced: under easy/sufficient, `belief` sometimes got the math
right too, because writing out the gap reconstruction *also* induces
chain-of-thought.

### 5.2 The double dissociation (confound resolved)

Adding the `naive_cot` arm isolates CoT from calibration:

|            | math (easy/suf → CORRECT) | calibration (hard/insuf → ABSTENTION) |
| :--------- | :-----------------------: | :-----------------------------------: |
| naive      | 0/5                       | 0/5                                   |
| naive_cot  | **5/5**                   | 0/5                                   |
| belief     | 1/5                       | **5/5**                               |

- CoT fixes math, not calibration: `naive_cot` solved 5/5 arithmetic but still
  confabulated 5/5 under insufficient context.
- Belief fixes calibration, not math: `belief` abstained 5/5 correctly but failed
  the arithmetic when data was present.

Two interventions, two effects, zero overlap. **You cannot get both from one
prompt** — the gap-check and the arithmetic compete for the same budget. This is
the empirical case for a *sequential* pipeline.

### 5.3 The pipeline gets both — on obvious gaps (20/20)

`proto_pipeline.py`: belief gate → (if PASS) REPL compute, with the context passed
into the REPL as a `context` variable so the arithmetic is *executed*, not mental.

```
                  math (suf→CORRECT)      calibration (insuf→ABSTENTION)
                  hard    easy            hard    easy
naive             0/5     0/5             0/5     0/5
naive_cot         0/5     5/5             0/5     0/5
belief            0/5     1/5             5/5     5/5
PIPELINE          5/5     5/5             5/5     5/5   ← only arm that gets ALL
```

The pipeline is the only arm filling all four quadrants — notably **hard/sufficient
= 5/5**, where every single-prompt arm scored 0/5 (51-number mental sum is
infeasible). The REPL executes the sum. Floating-point noise in the outputs
(`91800.00000000003`) is *evidence of real execution*, not a fabricated round
number.

It is also cheaper where it matters: gate-FAIL abstentions cost ~2.3 s / one stage,
versus naive burning tokens to confabulate a wrong answer.

### 5.4 The adversarial test — the gate's single point of failure (7/15)

The 20/20 only ever saw *whole ranges* removed (trivially detectable). The real
risk is a **false-pass**: the gate says "complete" when there's a subtle hole, and
the REPL then computes a wrong number *with the authority of execution* — more
dangerous than naive's obvious guess.

`proto_gate_adv.py` mutates the full oracle context:

- `complete`  — no gap (gate should PASS)
- `drop_mid`  — one ID removed from the *middle* of range A (should FAIL)
- `drop_last` — the last ID of range A removed (should FAIL)
- `drop_pair` — two adjacent IDs removed from range B (should FAIL)

Primary metric is the **gate decision itself** (because formulaic data could let a
model reconstruct a missing value, masking downstream harm).

| condition  | should | LLM-gate caught | mechanism |
| :--------- | :----: | :-------------: | :--- |
| drop_last  | FAIL   | **5/5** ✅       | removing the last ID shifts the visible range endpoint (200–219 ≠ 200–220) |
| drop_pair  | FAIL   | 2/5 ⚠️           | larger hole, sometimes visible |
| drop_mid   | FAIL   | **1/5** ❌       | interior ID gone, endpoints unchanged, range looks intact |
| complete   | PASS   | 5/5 PASS        | (but 1/5 REPL miscomputed even here) |

**False-pass rate: 7/15.** The mechanism is literally in the gate's own text: it
describes RECUPERADO as "IDs 300–320" even when 310 is missing — it reasons at
*range* granularity, so interior holes are invisible. The one `drop_mid` it caught
was the one where it happened to enumerate "(except ID_210)" — and whether it
enumerates or summarizes is non-deterministic.

A secondary break: on one `complete` case the gate correctly PASSed but the REPL
computed `7812.0` vs ground truth `36086.4` — wrong code on complete data. So the
20/20 was partly luck; the compute stage depends on generated-code quality.

### 5.5 The fix — REPL-grounded gate (0/15)

`proto_gate_repl.py`. The LLM emits *only* a declaration (~66 tokens):

```python
required_A = set(range(200, 220 + 1))
required_B = set(range(400, 420 + 1))
rate_A = 0.08
rate_B = 0.12
```

A deterministic harness then parses present IDs from the context, computes
`required − present` by set difference, and either FAILs with the exact missing
set or PASSes and sums the taxed values — all in the REPL.

| condition  | LLM-gate | REPL-gate |
| :--------- | :------: | :-------: |
| drop_mid   | 1/5 caught | **5/5 caught** |
| drop_last  | 5/5 caught | 5/5 caught |
| drop_pair  | 2/5 caught | **5/5 caught** |
| complete   | 5/5 PASS (1 miscompute) | 5/5 PASS, all correct |
| **FALSE-PASS** | **7/15** | **0/15** |

The killer cell — `drop_mid` — went 1/5 → 5/5. Set difference cannot miss the 210;
each FAIL even reports the exact gap (`missing_A=[210]`). And it is cheaper and
faster: ~66 tokens / ~1.5 s versus the LLM-gate's 1500–1900 tokens / ~8 s. **Less
LLM = better**, precisely because the part the LLM did badly became computation.

---

## 6. How to replicate

### 6.1 Setup

```powershell
pip install -r bench/requirements.txt   # requests, rank_bm25, python-dotenv, ...
Copy-Item .env.example .env
# edit .env: OPENROUTER_API_KEY=sk-or-v1-...   BENCH_MODEL=google/gemini-2.5-flash
```

Config is read from `.env` via `bench/config.py` (`load_dotenv()`); knobs:
`OPENROUTER_API_KEY`, `BENCH_MODEL`, `BENCH_TEMP` (default 0.0), `BENCH_TRIALS`.

### 6.2 Run the four experiments in order

```powershell
python -m bench.proto_belief      # 3 arms × 2 regimes × 2 difficulties × 5 variants
python -m bench.proto_pipeline    # sequential gate->REPL, 2x2
python -m bench.proto_gate_adv    # adversarial: subtle gaps, LLM gate (expect ~7/15 false-pass)
python -m bench.proto_gate_repl   # the fix: REPL-grounded gate (expect 0/15 false-pass)
```

Each writes a timestamped `results/<name>_<ts>.jsonl` (one row per eval, full
input/output/tokens/latency/cost) and prints its matrices + a summary block at the
end. Total cost for all four is well under USD 1.

### 6.3 What each result file contains

Every JSONL row carries: the condition/regime/difficulty/variant, the raw model
output (or REPL output), `gate` decision where applicable, `outcome`/`harm` label,
`parsed_value`, `ground_truth`, token counts, latency, and estimated cost. The
summary printed at the end is fully reconstructable from these rows.

### 6.4 Determinism notes

- `temperature=0` reduces but does not eliminate run-to-run variation (provider
  batching/routing). Treat single runs as indicative; the clean separations (0/40,
  20/20, 0/15) are robust, a 1-of-5 wobble is not.
- The REPL (`bench/repl.py::run_code`) uses a bare `exec()` and is **not
  sandboxed** — fine for a local benchmark, not for untrusted input. Harden before
  any deployment.
- Data is formulaic (`ID_N: R$ N*15`); a stronger model could in principle
  reconstruct a missing value from the pattern. That makes the adversarial test
  *conservative* — on real data without a closed form the gap matters more, not
  less.

---

## 7. Key files

| File | Role |
| :--- | :--- |
| `bench/config.py`        | env-based config (dotenv) |
| `bench/client.py`        | OpenRouter chat client, usage capture |
| `bench/pricing.py`       | real cost via OpenRouter `/api/v1/models` |
| `bench/evaluator.py`     | numeric parsing + `classify_outcome` (4-way taxonomy) |
| `bench/repl.py`          | `exec()` harness; `run_code(..., glb=)` injects `context` |
| `bench/proto_belief.py`  | naive / naive_cot / belief arms; 2×2 builder |
| `bench/proto_pipeline.py`| sequential belief-gate → REPL-compute |
| `bench/proto_gate_adv.py`| adversarial subtle-gap conditions; LLM gate |
| `bench/proto_gate_repl.py`| REPL-grounded gate (declare → set-diff → compute) |
| `IDEAS.md`               | running lab notebook with the full arc + paper links |

---

## 8. What this does and does not establish

**Establishes (on this task, this model):**
- Calibration and computation are separable axes a single prompt can't both serve.
- Decomposing them into sequential stages captures both.
- An LLM completeness gate is unreliable against interior gaps; reframing
  completeness as a deterministic set-difference eliminates the failure.
- The net effect is to shrink the LLM's role to intent→structure translation,
  pushing all checkable work onto the CPU — and this is cheaper and more reliable.

**Does not establish (open work):**
- Cross-model generality (only Gemini-2.5-flash tested).
- Real statistical power (temp=0 makes runs near-deterministic; vary phrasing for
  true n).
- Robustness of the *declaration* step — the LLM could still mis-translate a range
  (e.g. off-by-one on "inclusive"). Here it was 20/20, but a range-validation guard
  would harden it. Note the failure mode moved from "judgment" (hard) to
  "translation" (easy and checkable) — which is the point.
- Non-formulaic / unbounded data, and tasks where the required set isn't a clean
  range.

---

## 9. The one-line thesis

> Move determinism out of the LLM, one step at a time. First arithmetic, then
> completeness checking. What remains is the irreducible linguistic core — and the
> system gets cheaper, faster, and more reliable at every step.
