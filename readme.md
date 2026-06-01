# Decompose-the-Computation: a REPL-Grounded Gate for Retrieval Pipelines

**Status:** Empirical prototype report. Numbers from local runs, May–Jun 2026,
`google/gemini-2.5-flash` and `deepseek/deepseek-v4-flash` via OpenRouter,
`temperature=0`. Reproducible with the `bench/` harness in this repo.

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
5. This holds **across models** (0/15 on Gemini *and* DeepSeek, where the LLM-gate
   scored 7/15 and 2/15), survives **noisy/prose context** (model-written parser,
   8/8), and the residual weak point — the declaration step — fails only by
   *silently resolving genuine ambiguity*, fixed by making the interpretation
   explicit (ambiguity flagged 1/1, precise cases unharmed).
6. The approach **extends past enumerable sets** to *predicate*-defined
   requirements ("sum sales > 5000"): coverage needs a deletion-proof invariant
   (count/contiguity, not sorting), the invariant choice can be delegated to the
   LLM and validated deterministically (5/5), and a third verdict **UNDECIDABLE**
   handles predicates not evaluable from the data. Throughout, the system errs
   **only toward refusal, never toward false-certification** (§10).

The throughline: **every deterministic sub-task (arithmetic, completeness checking,
boundary interpretation, the coverage proof itself) is done better, cheaper, more
model-independently, and more reliably outside the LLM.** The LLM shrinks to its
irreducible, *checkable* role — translating natural-language intent into a structure
the CPU can verify. And the safety property is asymmetric by construction: honest
refusal, not confident error.

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

## 4. The experiments

All live in `bench/` and share the same evaluator, client, and ground-truth
machinery. Each is one runnable module. The first four (this section) establish the
core result; §10 adds the predicate-coverage extension.

| Module | Question it answers |
| :--- | :--- |
| `proto_belief.py`   | Does belief-reconstruction reduce confabulation? Is it just CoT? |
| `proto_pipeline.py` | Does a sequential gate→REPL pipeline get both calibration and math? |
| `proto_gate_adv.py` | Does the LLM gate survive *subtle* gaps? (adversarial) |
| `proto_gate_repl.py`| Does moving the gate into the REPL close the hole? (the fix) |
| `proto_gate_decl/2`, `proto_gate_noise` | Hardening: declaration ambiguity, noisy parsing (§5.6–5.8) |
| `proto_predicate`, `proto_coverage/2` | Predicate-defined coverage (§10) |

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

### 5.6 Hardening the residual SPOF — the declaration step

The REPL-gate's set difference is bulletproof, but the LLM still does one thing:
translate "IDs 200–250" into `set(range(...))`. We stress-tested that single step
with 8 boundary-ambiguous phrasings (`proto_gate_decl.py`), capturing the
*declared* set by executing the LLM's code and comparing to intent.

Result: **7/8 declared-set correct.** The pattern matters more than the score. The
model got the *objectively tricky* phrasings right — `[200, 250)` half-open →
`range(200, 250)`; "os 51 IDs a partir de 200" → `range(200, 200 + 51)` (wrote the
count arithmetic *in the code*, didn't do it in its head). The one miss was the only
*genuinely* ambiguous phrasing: "entre 200 e 250" → `{201..249}` (strictly between)
— a defensible reading, not an error.

So the residual failure isn't translation accuracy; it's **silent ambiguity
resolution**: the model picked one reading and didn't flag it, then the gate
computed perfectly against a possibly-wrong premise. The fix (`proto_gate_decl2.py`)
makes the declaration emit the set *plus* an `interpretation` string and an
`ambiguous` flag:

- Declared-set accuracy: 7/8 (unchanged — fix didn't hurt precise cases)
- Ambiguous phrasing flagged: **1/1** (was 0/1) — "entre" now marked ambiguous and
  verbalized ("read as exclusive, IDs 201–249")
- False-flag on precise phrasings: **0/7** (didn't become paranoid)

The point was never to "correctly" resolve an inherently ambiguous phrase — it was
to stop resolving it *silently*. A silent guess becomes a visible, confirmable
decision. (Same "make the belief explicit" move as the gate itself, one level up.)

### 5.7 Noisy-context parsing — the other dependency

The set difference is only as good as the present-set parsed from context. The
clean benchmark used perfectly formatted data; real exports are messy. We tested
the realistic deployment (`proto_gate_noise.py`) where the *model* writes the
extraction code, given context in four surface forms:

| style | example | recovered |
| :--- | :--- | :---: |
| clean | `ID_200: Venda de R$ 3000` | 11/11 |
| mixed_delim | `ID_200` / `ID-201` / `ID 202` / `id 203 ->` | 11/11 |
| annotated | `ID_200 [ok]`, `ID_201 (revisado)`, `// nota` | 11/11 |
| prose | `Transacao 200 no valor de R$ 3000.` | 11/11 |

**8/8 OK** (4 styles × full/missing-205). Even prose with no `ID_` prefix → 11/11,
and the real gap (missing 205) was flagged in every style. Parsing is not a hole:
told to write a parser for the format, the model handles realistic noise.

### 5.8 Cross-model — the strength is the model-independent part

We re-ran the adversarial gate and the REPL-gate on a second backbone
(`deepseek-v4-flash`):

|                       | Gemini-2.5-flash | DeepSeek-v4-flash |
| :-------------------- | :--------------: | :---------------: |
| LLM-gate FALSE-PASS   | 7/15             | 2/15              |
| REPL-gate FALSE-PASS  | **0/15**         | **0/15**          |

Two findings:

1. **REPL-gate = 0/15 on both models.** The strength is deterministic — set
   difference does not depend on the backbone.
2. **The LLM-gate fails *differently* per model (7 vs 2), which strengthens the
   case.** DeepSeek judges better in-head but still false-passes. The takeaway
   isn't "which model judges better" — it's that judgment has an irreducible,
   model-dependent, *unpredictable* error rate, whereas execution is 0 on any
   model. You can't predict how bad the LLM-gate will be; you can guarantee the
   REPL-gate is 0. (In one DeepSeek false-pass the gate text literally listed
   "IDs 400-409 e 411-420" — it saw the 410 was missing and concluded PASS anyway.)

The efficiency gap also widens on verbose models: DeepSeek's LLM-gate hit 3308
tokens / 86 s in one case; its REPL-gate stayed ~60–280 tokens / 3–8 s. More
"thinking" means more expensive judgment, so deterministic gating wins harder.

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

### 6.2 Run the experiments in order

```powershell
python -m bench.proto_belief      # 3 arms × 2 regimes × 2 difficulties × 5 variants
python -m bench.proto_pipeline    # sequential gate->REPL, 2x2
python -m bench.proto_gate_adv    # adversarial: subtle gaps, LLM gate (expect ~7/15 false-pass)
python -m bench.proto_gate_repl   # the fix: REPL-grounded gate (expect 0/15 false-pass)
python -m bench.proto_gate_decl   # audit the declaration step (8 ambiguous phrasings)
python -m bench.proto_gate_decl2  # the declaration fix (explicit interpretation + ambiguous flag)
python -m bench.proto_gate_noise  # model-written parser vs noisy context (4 styles)
python -m bench.proto_predicate   # predicate coverage: weak vs deletion-proof invariant
python -m bench.proto_coverage    # LLM declares coverage invariant; REPL validates
python -m bench.proto_coverage2   # adversarial labels + UNDECIDABLE verdict
```

For the cross-model run, set `BENCH_MODEL` to a non-Gemini backbone (e.g.
`deepseek/deepseek-v4-flash`) and re-run `proto_gate_adv` + `proto_gate_repl`.

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
| `bench/proto_gate_decl.py`| audits the declaration step (boundary-ambiguous phrasings) |
| `bench/proto_gate_decl2.py`| declaration fix: explicit interpretation + ambiguous flag |
| `bench/proto_gate_noise.py`| model-written parser vs noisy/prose context |
| `bench/proto_predicate.py`| predicate coverage: weak vs deletion-proof invariant |
| `bench/proto_coverage.py`| LLM declares the coverage invariant; REPL validates (2 gates) |
| `bench/proto_coverage2.py`| adversarial labels + UNDECIDABLE verdict |
| `plugins/belief-gate/`   | the technique packaged as a Claude Code skill |
| `IDEAS.md`               | running lab notebook with the full arc + paper links |

---

## 8. What this does and does not establish

**Establishes (on this task family, two models):**
- Calibration and computation are separable axes a single prompt can't both serve
  (double dissociation).
- Decomposing them into sequential stages captures both (20/20).
- An LLM completeness gate is unreliable against interior gaps (7/15 Gemini, 2/15
  DeepSeek); reframing completeness as a deterministic set-difference eliminates
  the failure (**0/15 on both models**).
- The residual SPOF is the declaration step, and its failure is *silent ambiguity
  resolution*, not translation error — fixed by surfacing the interpretation
  (ambiguity flagged 1/1, precise cases unharmed 0/7 false-flag).
- The model-written parser survives noisy/prose context (8/8).
- **Predicate-defined requirements** (no enumerable set) extend the gate: coverage
  needs a *deletion-proof invariant* (count or contiguity; sorting is an illusion),
  the invariant choice can be delegated to the LLM and validated in two gates
  (5/5), and a third verdict UNDECIDABLE handles predicates not evaluable from the
  data. See §10.
- The system errs **only toward refusal**, never toward false-certification —
  verified leak-proof across all declared claims (§10.4).
- Net effect: shrink the LLM to intent→structure translation, push all checkable
  work onto the CPU — cheaper, faster, model-independent, and more reliable.

**Does not establish (open work):**
- Real statistical power (temp=0 makes runs near-deterministic; vary phrasing /
  seeds for true n). The clean separations (0/15 twice, 8/8, 5/5, double
  dissociation) are robust; a 1-of-5 wobble is not.
- The precise boundary of fundamentally-undecidable predicates, and the small
  `claim_total`-validation hardening that recovers the one over-abstain (§10.5).
- Untrusted input (the REPL is bare `exec()`), and domains where there is no
  closed-form fallback to recover a missing value.

---

## 9. Composing the pieces — the gate-REPL as one system (concept)

The four experiments produced separable components. Composed, they form a single
context-grounded answering pipeline. This section describes the concept and method;
it is the integration target, not yet a measured end-to-end system.

### 9.1 Components and their proven properties

| Component | Job | Proven property |
| :--- | :--- | :--- |
| **Declare** | task NL → `required` set + rates + interpretation | precise 7/7; ambiguity surfaced 1/1 |
| **Parse** | context → `present` set (model-written, noise-robust) | 8/8 incl. prose |
| **Gate** | `required − present` in executed code | 0/15 false-pass, two models |
| **Recover** | on gap, read missing value from a source (file/query) | R1/R2 manual; never estimates |
| **Compute** | on PASS, do the deterministic work in code | exact via execution |

### 9.2 Control flow

```
task + context
     │
     ▼
[Declare]  LLM emits: required set, rates, interpretation, ambiguous?
     │           └─ if ambiguous → surface interpretation, ask/confirm
     ▼
[Parse]    model writes a parser for THIS context → present set
     │
     ▼
[Gate]     gap = required − present        (executed, deterministic)
     ├─ gap empty ────────────────► [Compute] → FINAL
     └─ gap non-empty
            │
            ▼
        [Recover] is a source available (file/query)?
            ├─ yes → read the missing items → re-run [Gate]
            └─ no  → ABSTAIN, report the exact gap   (never estimate)
```

### 9.3 The invariant that makes it safe

Every decision that *can* be deterministic *is* — completeness (set difference),
recovery (read, don't estimate), arithmetic (execute, don't reason). The LLM
contributes only the two genuinely linguistic acts: translating intent into a
required set, and writing a parser for an unseen format. Each of those is
**checkable** (the declared set can be echoed back; the parser's recovered set can
be re-verified), unlike the original act it replaced (judging completeness in the
head), which was not.

### 9.4 Where it still needs a human or a fallback

- **Ambiguous intent.** When the declaration flags ambiguity, the safe path is to
  confirm with the user, not to proceed on a guess.
- **No recovery source.** If the gap can't be filled from a real source, the
  pipeline abstains — by design, not failure.
- **Non-enumerable requirements.** §10.

---

## 10. Predicate-defined requirements — from set difference to coverage proof

The gate so far works because the requirement is an *enumerable set*: `{200..250}`,
twelve months, a list of invoices. Many real tasks define the requirement by a
*predicate* — "all sales above 5000", "every customer flagged in the audit". There
is no a-priori set to diff against; membership depends on data you may not fully
have. Completeness becomes a **coverage** question: *have I seen every record the
predicate could select?* Three experiments (`proto_predicate.py`,
`proto_coverage.py`, `proto_coverage2.py`) close this frontier on
`deepseek-v4-flash`.

### 10.1 Coverage needs a deletion-proof invariant (not just determinism)

`proto_predicate.py` — predicate "sum sales > 5000", 5 scenarios, three arms: an
LLM judge, a deterministic verifier that accepts *sorted + boundary crossed* as
proof (`weak`), and one that demands a *deletion-proof* invariant (`robust`).

| arm | correct | fails on |
| :--- | :---: | :--- |
| llm_judge   | 4/5 | mid-deletion (judges coverage in-head) |
| repl_weak   | 4/5 | mid-deletion (deterministic, **wrong invariant**) |
| repl_robust | 5/5 | — |

The pivotal scenario is **mid-deletion**: a sorted list with one qualifying record
removed from the middle. The list is *still sorted* and the boundary is *still
crossed*, so `repl_weak` — though fully deterministic, no LLM — certifies COMPLETE
and computes a wrong sum. It and the LLM judge even emit the *same* wrong number
(659968): they share the fallacy "sorted ⇒ complete." Only `repl_robust`, which
requires `full_count` or contiguous IDs, catches it.

> **The refinement this forces on the whole thesis:** moving to execution only
> helps if you execute over the invariant that *actually proves the property*.
> Determinism over the wrong invariant fails as silently as judgment. The hard part
> isn't "run code" — it's identifying which invariant is deletion-proof. The
> enumerable gate got that proof for free (the required set *was* the contiguity
> guarantee); the predicate strips the crutch and makes it explicit.

### 10.2 The invariant choice can be delegated to the LLM and stay safe

`proto_coverage.py` moves the "which proof applies?" choice from a hardcoded
verifier into a **checkable LLM declaration**. The LLM reads the source description
and declares `claim_kind` ∈ {`full_count`, `contiguous_ids`, `sorted_to_threshold`,
`none`} plus a total. The REPL validates two gates: (a) is the kind deletion-proof?
(b) does it hold in the data? CERTIFY only if both.

| arm | correct | tokens |
| :--- | :---: | :---: |
| llm_only  | 3/5 (2 false-complete) | ~29k |
| declared  | **5/5** (0 false-complete) | ~16k |

The reveal is in *how* the model decided. It declared the correct coverage category
in all five. On the trap scenario, free-judging (`llm_only`) it false-completed
(659968 again); **forced to declare the invariant, the same model chose `none`** —
it *knows* "sorted + complete export" doesn't prove coverage; it just doesn't use
that knowledge when left to judge freely. The two-gate validator means the LLM can
err in **both** directions — pick a weak invariant (rejected on kind, even when the
weak claim is *true*) or lie a strong one (rejected on data) — and the system never
false-completes. And it used half the tokens: declaring a short claim is cheaper
than rationalizing coverage in prose.

### 10.3 Lying labels and the undecidable case

`proto_coverage2.py` adds a third verdict, **UNDECIDABLE**, and probes two edges.

**Adversarial source labels.** A source labelled "complete, 200 rows" that actually
ships 140 (or claims contiguous IDs with one mid-deleted). Even when the LLM
*believes the label* and mis-declares, `len(records) == claimed_total` fails and the
verdict is INCOMPLETE. A false completeness label cannot survive an actual count —
**the data gate, not the LLM's trust, carries the guarantee.**

**The undecidable predicate.** "Sum of FLAGGED customers", where flagged-ness comes
from an external audit *not in the records*. Here even `full_count=200` (perfect
coverage) doesn't help: the predicate cannot be evaluated from the data at all. The
honest answer is UNDECIDABLE — distinct from INCOMPLETE (a proved gap) and COMPLETE
(a proved sum). DeepSeek declared `undecidable` **spontaneously**, recognizing that
*seeing every record doesn't help when the property defining membership lives
outside the data.* **Coverage and evaluability are different axes**; full coverage
does not imply a decidable predicate.

Score: 4/5. The one miss is instructive — on a decidable flagged case the LLM put
the *expected answer* (129291) into `claim_total` instead of the record count (200);
the validator checked `len == 129291`, failed, and returned INCOMPLETE. That is the
validator working: a declaration slip (count vs answer) was rejected to the **safe
side** — over-abstain, not false-complete. Same class as the "entre" off-by-one: a
checkable translation error, not a judgment error.

### 10.4 The safety asymmetry

Across every predicate experiment the system errs **only toward refusal**
(over-abstain), **never toward false-certification**. No incomplete or undecidable
scenario was ever certified COMPLETE — verified leak-proof offline across all
possible declared claims, and confirmed in every run. For a safety gate this is the
correct asymmetry: refusing a valid task is tolerable; certifying an invalid one is
catastrophic. The system only ever makes the tolerable error.

### 10.5 Where completeness is still fundamentally undecidable

The honest boundary: when a predicate's qualifying set cannot be bounded by *any*
invariant obtainable from the source — no count, no key contiguity, no sort that
brackets membership — coverage is undecidable in principle, not merely unproven. The
right system output there is UNDECIDABLE with a statement of what would be needed
(an authoritative count, the missing field), not a guess. Mapping that boundary
precisely, and the small `claim_total`-validation hardening that would recover the
4/5 case, are the remaining open items.

---

## 11. The one-line thesis

> Move determinism out of the LLM, one step at a time — arithmetic, then
> completeness checking, then boundary interpretation, then the coverage proof
> itself. What remains is the irreducible, *checkable* linguistic core: translate
> intent into a structure the CPU can verify. The system gets cheaper, faster,
> model-independent, and — crucially — it errs only toward honest refusal, never
> toward confident wrong answers.
