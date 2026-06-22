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
python -m bench.proto_coverage3   # self-consistency repair loop + undue-undecidable gate
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
| `bench/proto_coverage3.py`| self-consistency repair loop + undue-undecidable gate |
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
- Declaration errors are recovered without losing safety: a self-consistency repair
  loop fixes form slips and a deterministic gate rejects undue `undecidable` — both
  arms 4/4, 0 false-complete (§10.4).
- The system errs **only toward refusal**, never toward false-certification —
  verified leak-proof across all declared claims (§10.5).
- Net effect: shrink the LLM to intent→structure translation, push all checkable
  work onto the CPU — cheaper, faster, model-independent, and more reliable.

**Does not establish (open work):**
- Real statistical power (temp=0 makes runs near-deterministic; vary phrasing /
  seeds for true n). The clean separations (0/15 twice, 8/8, 5/5, 4/4, double
  dissociation) are robust; a 1-of-5 wobble is not.
- The precise boundary of fundamentally-undecidable predicates where no count
  exists even in principle (§10.6).
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
predicate could select?* Four experiments (`proto_predicate.py`,
`proto_coverage.py`, `proto_coverage2.py`, `proto_coverage3.py`) close this frontier
on `deepseek-v4-flash`.

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
checkable translation error, not a judgment error. §10.4 recovers it generically.

### 10.4 Self-consistency repair — recovering declaration slips without losing safety

The 4/5 miss was a *correctable* slip: the task was decidable, the system just
refused it. The tempting fix — special-case `claim_total` — is not generalist.
`proto_coverage3.py` instead adds a **declare → check-consistency → (repair)\* →
decide** loop. The consistency check is generic: it flags any declared field that
cannot be reconciled with the data (e.g. a total that equals an aggregate of the
values rather than a record count) and returns a precise diagnostic; the LLM
re-declares; only then does `decide()` run. This is the *third side* of the
guarantee — never false-complete, abstain honestly when undecidable, and now **don't
refuse a correctable slip.**

Two arms over 4 scenarios: a real model, and a `buggy_first` declarer that *always*
mis-places the answer value into `claim_total` on attempt 1 (to isolate whether the
loop, not model luck, recovers it). Result: **both arms 4/4, 0 false-complete.**
`buggy_first` recovers every scenario via one repair round.

Two findings the loop surfaced:

1. **The repair must not invent the answer from visible data.** An offline check
   caught a near-bug: a naive repair that declares `claim_total = len(present)` would
   re-introduce false-complete on partial data (140 present "repaired" to 140 →
   certified). The fix: repair reads the *source's* claimed total (the "200 de 200"
   label), never the present count. **The diagnostic points at the error but must not
   suggest the answer from the data — suggesting it from the data is the very
   anti-pattern the system exists to prevent.** With this, `partial` is repaired to
   200, still ≠ 140 present → correctly INCOMPLETE.

2. **Two distinct declaration-error classes — both now caught.** A *form* slip (value
   in the count field) is incoherent with the data → caught. A *judgment* error
   (declaring `undecidable` for a decidable predicate) is internally coherent, just
   wrong — so it needs a semantic gate. We added one: `predicate_evaluable()` is
   deterministic (`sum_gt` always; `flagged_sum` iff a flag field is present), so
   `check_consistency` rejects an `undecidable` declaration when the predicate *is*
   evaluable and asks for a coverage invariant instead. This closed the last gap
   (the real model went 3/4 → 4/4), while leaving the *legitimate* undecidable
   (external flag, predicate genuinely not evaluable) untouched. The asymmetry the
   gate keys on — evaluability — is something `decide()` already computed; we just
   moved the decidability judgment itself into a checkable gate.

| LLM error                        | caught by         | recovers to |
| :------------------------------- | :---------------- | :---------- |
| form slip (value in count field) | check_consistency | re-declare  |
| judgment (undue `undecidable`)   | check_consistency | re-declare  |
| valid but source-incomplete      | decide()          | INCOMPLETE  |
| predicate not evaluable          | decide()          | UNDECIDABLE |

### 10.5 The safety asymmetry

Across every predicate experiment the system errs **only toward refusal**
(over-abstain), **never toward false-certification**. No incomplete or undecidable
scenario was ever certified COMPLETE — verified leak-proof offline across all
possible declared claims, and confirmed in every run, including through the repair
loop (neither slip-repair nor the undecidable gate ever traded safety for
completeness). For a safety gate this is the correct asymmetry: refusing a valid
task is tolerable; certifying an invalid one is catastrophic. The system only ever
makes the tolerable error.

### 10.6 Where completeness is still fundamentally undecidable

The honest boundary: when a predicate's qualifying set cannot be bounded by *any*
invariant obtainable from the source — no count, no key contiguity, no sort that
brackets membership — coverage is undecidable in principle, not merely unproven. The
right system output there is UNDECIDABLE with a statement of what would be needed
(an authoritative count, the missing field), not a guess. Mapping that boundary
precisely is the remaining open item; the declaration-slip and undue-undecidable
gaps are now closed (§10.4).

---

## 11. Real-benchmark study — where the gate wins, ties, and loses

The synthetic results above use regular `ID_N:` data. To find the real boundary we
ran three benchmarks against three baselines (naive RAG, an LLM "sufficient-context"
judge, and CoT self-critique), on real text and real financial tables.
`bench/bench_niah.py`, `bench/realqa/`.

### 11.1 Results, honestly

| Benchmark | Data | Result for belief-gate |
| :--- | :--- | :--- |
| Multi-needle (NIAH) | 3430 lines of real paper text, 8 named needles | **Accuracy ties.** Obvious gaps; the LLM-judge already counts them. The gate's edge is property (constant cost, proof), not score. |
| FinQA (gold support) | real 10-K tables, drop a gold supporting cell | **Does not apply.** Required set is annotation-derived; the key vanishes with the dropped item. Open-QA regime. |
| Keyed aggregation (LLM extractor) | real FinQA tables, sum question-named columns, drop one | **Mid-pack** (false-suff 2/40 vs judge 1, cot 2, naive 3). Cheapest by 2×. Both error types were *extractor* failures. |
| Keyed aggregation (**deterministic** extractor) | same, but `present` parsed from the rendered header — no LLM in the decision | **Clean 0/40 + 0/40 at 0 tokens** (see §11.2a). Ties the best LLM arm on accuracy, wins decisively on cost + guarantee. |

> **Update — the real-FinQA-QA regime (path C, [FINQA.md](FINQA.md)).** A later study built a
> gate for the *actual* FinQA questions (not keyed aggregation) — an operand-grounding gate over
> model-emitted programs — and measured it across 5 models. There the gate does **not** beat a
> calibrated `direct` baseline on confabulation: on real QA the failure is *misselection* (a
> present-but-wrong number), which operand-grounding cannot catch. The honest claim shrinks to
> *execution buys accuracy; the gate makes execution safe* — not *the gate makes a model more
> honest than asking it directly*. The keyed-aggregation results in this section remain valid for
> their regime (enumerable, task-derived required set); do **not** generalize the 80/20 / 0-cost
> wins below to open numeric QA.

### 11.2 The boundary the three benchmarks measured (not asserted)

The lib's core (set difference, coverage verification) is flawless — 29/29 unit
tests, leak-proof. The weak point in real data is the **extractor that produces the
`present` set**. When that extractor is an LLM transcribing strings from messy
text/tables, you reintroduce the judgment the gate exists to remove, *at the edge* —
and the guarantee blurs (long near-identical headers mismatch; an unparsed list
yields empty `present` and a false alarm).

So the scope, measured:

- ✅ **Structured/parseable `present` + task-derived `required`** → the gate wins
  (0/15 false-pass): the original `ID_N:` regime, a DB query, an API, a deterministic
  format parser. The key survives the datum's absence because the *task* names it.
- ⚠️ **LLM-extracted `present` from prose/messy tables** → the extractor is the floor,
  not the gate.
- ❌ **Relevance only knowable by understanding the data (open QA)** → the gate needs
  a relevance oracle it doesn't have; pair it with an LLM, don't use it alone.

This is not a retreat from the synthetic result — it explains it. The fiscal scenario
was not a convenient toy; it was *exactly* the regime where the gate applies. The
real benchmarks bounded that regime by honest elimination, and turned the lib
README's central claim ("enumerable, task-derived requirement; structured present")
into a measured rule rather than an assertion.

### 11.2a The pre-registered prediction, tested

§11.2 made a falsifiable claim: *the keyed-aggregation tie was the LLM extractor, not
the gate.* If true, replacing the LLM that lists headers with a **deterministic parse**
of the rendered header row (exact match of the task's named columns) should erase both
error types. We pre-registered this (predictions + falsifiers, in `IDEAS.md`) before
running, then ran both arms side by side on the same 40 real tables.

| method | false-suff (insufficient) | over-abstain (complete) | ~tokens |
| :--- | :--- | :--- | :--- |
| rag_naive | 0/40 | 0/40 | 55,712 |
| llm_judge | 0/40 | **6/40** | 46,004 |
| llm_cot | 1/40 | 1/40 | 70,171 |
| belief_gate (LLM extractor) | 0/40 | **7/40** | 28,249 |
| **belief_gate_det** (deterministic) | **0/40** | **0/40** | **0** |

What this confirms — and what it doesn't:

- **Prediction held in spirit.** With `present` parsed deterministically, the gate
  posts a clean 0 dangerous + 0 over-abstain at **zero model cost**. The 7 over-abstains
  of the LLM-extractor arm vanished — proving they were the *extractor*, not the gate.
- **Honest caveat on "win."** `rag_naive` also scored 0/0 on this subset (the
  named-column drop was salient enough for a careful computing model to refuse). So the
  deterministic gate **ties the best baseline on accuracy** and wins on the other two
  axes: **cost** (0 vs 55,712 tokens) and **guarantee** (its 0 is structural and
  leak-proof by construction; naive's 0 is empirical luck on this draw — the same naive
  arm scored 3 false-suff on the earlier subset). This matches the NIAH lesson: the
  gate's edge is *property*, not *score*.
- **One falsifier fired, then was diagnosed.** Prediction "false-suff → 0" failed on
  first contact (2/40), both on a table with **duplicate column headers** — two columns
  literally named `december 31 2014 unfunded`. Dropping one left the other, so the
  required *name* was genuinely still present and the gate said COMPLETE *correctly*;
  the test oracle was mislabeled. Fix (post-hoc, exploratory): require uniquely-named
  columns — a name-key proves absence only if it uniquely identifies the column, the
  deletion-proof principle one level up. After the fix: 0/40. Reported as "0/0 after
  fixing a duplicate-header oracle bug," not "0/0 as predicted."

### 11.2b Multi-model power: the single-model tie does not survive a second model

The single-model run left an honest caveat: `rag_naive` also scored 0/0, so the
deterministic gate only *tied* on accuracy. Running a second model (and a deepseek
test-retest) dissolves that caveat. Pooled over **two models × 120 decisions per
condition** (deepseek-v4-flash ×2 draws + gemini-2.5-flash; clean post-fix files only):

| method | FALSE-SUFF (dangerous) | over-abstain | ~tokens |
| :--- | :--- | :--- | :--- |
| rag_naive | **16/120** | 1/120 | 85,348 |
| llm_judge | 2/120 | **30/120** | 58,471 (+22 unparseable) |
| llm_cot | 3/120 | 1/120 | 111,927 (+22 unparseable) |
| belief_gate (LLM extractor) | 0/120 | **39/120** | 40,247 |
| **belief_gate_det** | **0/120** | **0/120** | **0** |

Per-model, the failures are severe and *move around*:

- **gemini-2.5-flash, `rag_naive`: 14/40 (35%) false-sufficient.** Asked to just compute
  the sum, a strong model confidently confabulates a total for a table missing a required
  column more than a third of the time. This is the exact confident-confabulation failure
  the whole project targets — and it is *worse* on the stronger model, not better.
- **gemini, `belief_gate` (LLM extractor): 28/40 (70%) over-abstain.** The header-listing
  extractor collapses on gemini — re-confirming §11.2 (the extractor is the floor) and
  showing that floor is model-dependent and can be very low.
- **gemini, `llm_judge`/`llm_cot`: 22/40 outputs unparseable** by the SUFFICIENT/
  INSUFFICIENT regex. The LLM arms are fragile to output *format* across models; their
  gemini rates are computed on < half the cases and are not trustworthy. The deterministic
  arm has no parsing surface to break.
- **deepseek test-retest (same seed, same 40 cases, temp 0):** `llm_judge` over-abstain
  swung 6 → 22 between two runs; `rag_naive` false-suff 0 → 2. Even fixing model and
  cases, the LLM arms are not reproducible run-to-run. The deterministic arm is
  bit-identical every time.

**The corrected headline.** `belief_gate_det` is the *only* method that is simultaneously
(a) zero dangerous errors, (b) zero false alarms, (c) zero token cost, and (d)
bit-reproducible — and it holds all four on **both** models. Every LLM arm fails at least
one of these on at least one model, and *which* one it fails is not predictable in
advance. On gemini specifically there is **no** clean LLM baseline (naive 14 FS, judge
unreliable, cot unreliable, LLM-gate 70% over-abstain), so the deterministic gate is not
tying a baseline — it is the only method left standing. The single-model "tie" was an
artifact of one lucky model; cross-model, the property-based guarantee is the whole point.

> Data-hygiene note: the pooled table uses only the three post-unique-header-fix files
> that contain the `belief_gate_det` arm. An earlier pre-fix run (no det arm) was
> excluded; `aggregate_keyed.py` now warns when mixing files with different method sets
> would make denominators disagree.

### 11.2c Where the open-QA grounding guardrail did NOT earn its keep (negative result)

We also tested the *other* role of the gate — a post-answer **grounding guardrail** for
open QA, where the answer is not a computation (`bench/openqa/harness_claimgate.py`). The
LLM answers an extractive cell-lookup question; a deterministic check verifies the
answered value is present in the source; we compare it to the LLM judging its own
grounding. Unanswerable cases are induced by blanking the target cell while keeping its
row label and column header (so absence is non-obvious).

The finding is negative and worth stating plainly: **modern models do not confabulate on
single-fact extractive lookup when an abstention path is offered.** Across deepseek-v4-flash
and gemini-3.1-flash-lite (n=40 each, cellblank), real-value confabulation was **0** — both
abstained correctly when the cell was blank; gemini-3.1-flash-lite was perfect (40/40
answerable, 40/40 abstain). The guardrails had nothing to catch except 2 malformed/empty
outputs, where the deterministic check still beat the LLM autorater (2/2 vs 1/2).

The contrast with §11.2b is the real lesson — **confabulation is regime-dependent:**

| Regime | Framing | Confabulation |
| :--- | :--- | :--- |
| Keyed aggregation (§11.2b) | "compute the sum", column silently dropped, abstention not emphasized | gemini-2.5 **35%** |
| Extractive lookup (§11.2c) | "what is cell X? reply NOT FOUND if absent", local blank signal | **0%** |

So the confident-confabulation failure the gate defends against lives in the
**compute / multi-fact** regime (where you verify completeness *before* computing — the
gate's home turf), *not* in clean single-fact lookup, where the model self-abstains. A
post-answer grounding checker is a solution looking for a problem there. The one untested
avenue where it might still matter is long-form, multi-claim answers — not measured here.

### 11.3 The load-bearing rule for users

> Feed `present` from a parser / DB / API, not from an LLM reading prose. Derive
> `required` from the task, not from the data. Inside that envelope the guarantee is
> absolute (never false-completes); outside it, the gate degrades to whatever
> produced its inputs.
>
> And: reach for the gate in the **compute/aggregate/multi-fact** regime, where models
> confabulate confidently — not for single-fact extractive lookup, where they already
> abstain well on their own.

---

## 11.4 The end-to-end payoff: LLM → gate → REPL → answer (the double dissociation)

Everything above measured the gate's *decision*. The final experiment measures the full
system producing the *answer*, and decomposes where each piece pays
(`bench/realqa/harness_pipeline.py`). Task: "sum all numeric values in columns X, Y, Z" over
real FinQA tables (compute regime). COMPLETE = full table (a correct answer exists);
INSUFFICIENT = a required column removed (correct behavior = abstain). Three arms isolate the
contributions: `llm_direct` (no gate, no REPL), `gate+llm_compute` (gate gates, LLM computes),
`gate+repl` (gate gates, REPL computes). Pooled over deepseek-v4-flash + gemini-2.5-flash, 80 each:

| arm | COMPLETE correct | wrong# | over-abstain | INSUFF abstain | INSUFF confab |
| :--- | :--- | :--- | :--- | :--- | :--- |
| llm_direct | 3/80 | 53 | 24 | 77/80 | 3 |
| gate + llm_compute | 6/80 | 73 | 0 | 80/80 | 0 |
| **gate + repl** | **80/80** | 0 | 0 | **80/80** | 0 |

The arithmetic axis is devastating for the LLM: **gemini-2.5 scored 0/40** on COMPLETE (every
sum wrong — gold 3,151,435 → "2,600,000"); deepseek 3–6/40. LLMs cannot reliably sum ~15–20
formatted financial cells. The REPL does it perfectly, free.

The **double dissociation**, in one table:
- the **gate** alone removes the dangerous INSUFFICIENT-confabulation (→0) but not the
  COMPLETE-arithmetic error (still 6/80 — the LLM still computes);
- the **REPL** on top fixes the arithmetic (→80/80) and inherits the gate's abstention;
- **only the full LLM→gate→REPL is correct-or-abstains on both axes.**

This is the project's origin dissociation (CoT fixes arithmetic; belief-reconstruction fixes
calibration) in its *deterministic* form — and the deterministic versions dominate the LLM
versions. So gate + REPL is not just a verifier: for a **computable** question it is a QA
*system* that answers exactly or abstains, never a confident wrong total.

Honest scope (pre-registered): gate+repl's 80/80 on COMPLETE is correct-by-construction (it
computes the same gold); the non-trivial finding is that the LLM arms sit at 3–6/80 — the LLM
is the wrong tool for exact arithmetic. The task is arithmetic-heavy on purpose (the compute
regime); for single-fact lookup the LLM is fine and the pipeline adds little (§11.2c). The
translation step (question → required set) was trivialized on purpose to isolate compute+gate
from the extractor-is-the-floor problem (§11.2).

---

## 12. The one-line thesis

> Move determinism out of the LLM, one step at a time — arithmetic, then
> completeness checking, then boundary interpretation, then the coverage proof
> itself. What remains is the irreducible, *checkable* linguistic core: translate
> intent into a structure the CPU can verify. The system gets cheaper, faster,
> model-independent, and — crucially — it errs only toward honest refusal, never
> toward confident wrong answers.
