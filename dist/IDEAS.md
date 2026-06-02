# IDEAS — research log & open threads

Running log of ideas, paper connections, and experiment results that emerged
alongside the `bench/` work. Not a polished writeup — a lab notebook.

---

## The unifying thread: "belief ≠ reality"

Multiple recent papers and our own experiments are attacking the *same* failure
mode in different substrates: **a model anchors on a contaminated/incomplete
representation of its information state instead of the actual evidence.**

| Substrate where the fix lives | Work | Mechanism |
| :--- | :--- | :--- |
| User's mind (inference scaffold) | UserHarness (Qian et al., 2026) | reconstruct observe→believe→intend→act |
| Token distribution (training) | Canonical Context / CCOPD (Lin et al., 2026) | reverse-KL distill student→canonical teacher |
| Retrieval pipeline (inference scaffold) | **our belief-aware RAG** | reconstruct REQUER/RECUPERADO/LACUNA |
| Consolidated skill (offline distill) | Trace2Skill (Ni et al., 2026) | parallel patch + conflict-free merge |
| Latent vector (online + REM) | Aura / LCO | project onto compliance manifold |
| Deterministic execution | RLM / CodeAct | move computation off the probabilistic substrate |

All answer: *how do we stop the model from anchoring on its own contaminated
assumptions instead of the real evidence?* Nobody has unified these.

---

## Paper: Canonical Context / CCOPD (Lin et al., Zhejiang, May 2026)

arXiv:2605.30251 — "Same Evidence, Different Answers."

**Phenomenon — self-anchored drift:** model solves a task with a FULL prompt
but fails when the SAME evidence arrives sharded across turns (RAW-SHARDED),
because the history contains the model's own earlier partial replies, which
carry unsupported assumptions it then anchors on at the final turn.

**Formalization:** canonical-context consistency via
`Ψπ(q,s) = D_KL( π(·|h(q),s) ‖ π(·|c(q),s) )` where `h` = contaminated history,
`c` = canonical FULL context. Ψ > 0 means drift.

**Method — CCOPD:** same base model, two roles. Frozen teacher on FULL prompt;
trainable student on sharded conversation. Token-level **reverse-KL** supervision
on the student's own answer prefixes re-anchors it to the teacher's canonical
distribution. Trained only on GSM8K math conversations.

**Results:** +32% relative on RAW-SHARDED across math + 5 zero-shot OOD families,
preserves FULL-context performance. Ablation: reverse-KL > forward-KL
(mode-seeking re-anchoring beats mode-covering).

**Connections to our work:**
- Same failure mode as our RAG confabulation, different cause (own history vs
  incomplete retrieval) and different reference (FULL prompt vs task requirement).
- CCOPD fixes via *training* (internalized in weights); our belief-aware and
  UserHarness fix via *inference-time scaffold* (zero training, reversible).
  → This is the "coin" again: train-for-capability vs virtualize-via-interface.
- The reverse-KL insight validates our binary belief prompt: re-anchoring should
  *collapse to the correct mode*, not hedge over possibilities.
- Multi-agent implication: drift compounds across autonomous handoffs — exactly
  the risk of the compound/LCO paradigm. Aura's compliance_manifold is a latent-
  space cousin of canonical re-anchoring.

**Open hypothesis (needs LoRA, out of cheap scope):** belief-aware (inference)
vs CCOPD (training) — what fraction of the drift gap does each close, and are
they additive? If additive → a paper.

---

## Experiment: Belief-Aware Retrieval (DONE)

Claim: a retrieval pipeline that explicitly reconstructs {required, retrieved,
gap} before answering reduces confident confabulation, converting it to honest
abstention — without changing the retriever.

Code: `bench/proto_belief.py`, `bench/evaluator.py::classify_outcome`.
Control: all conditions see the EXACT same retrieved context per trial; only the
prompt scaffold differs.

### Outcome taxonomy (mutually exclusive)
- CORRECT — right number
- ABSTENTION — acknowledges gap (keyword or non-empty LACUNA), no committed number
- CONFABULATION — wrong number under INSUFFICIENT context (false belief)
- ARITHMETIC_FAIL — wrong number under SUFFICIENT context (had data, miscomputed)

### Conditions
- naive — answer directly
- naive_cot — "think step by step, show calculations", NO belief reconstruction
- belief — reconstruct REQUER/RECUPERADO/LACUNA, then answer or abstain

### Final results (google/gemini-2.5-flash, 5 variants × 2 regimes × 2 difficulties × 3 conditions)
Files: results/belief2x2_20260531_151716.jsonl (3-arm),
       belief2x2_20260531_111655.jsonl (2-arm), belief_20260531_104024.jsonl (first)

```
2x2 MATRIX [HARD arithmetic]
              sufficient ctx        insufficient ctx
naive         ARITHMETIC_FAIL 5/5   CONFABULATION 5/5
naive_cot     ARITHMETIC_FAIL 4/5   CONFABULATION 5/5
belief        ARITHMETIC_FAIL 5/5   ABSTENTION    5/5

2x2 MATRIX [EASY arithmetic]
              sufficient ctx        insufficient ctx
naive         ARITHMETIC_FAIL 5/5   CONFABULATION 5/5
naive_cot     CORRECT 5/5           CONFABULATION 5/5
belief        ARITHMETIC_FAIL 4/5   ABSTENTION    5/5
```

### THE DOUBLE DISSOCIATION (the key result)

|            | math (easy/suf → CORRECT) | calibration (hard/insuf → ABSTENTION) |
| :--------- | :-----------------------: | :-----------------------------------: |
| naive      | 0/5                       | 0/5                                   |
| naive_cot  | **5/5**                   | 0/5                                   |
| belief     | 1/5                       | **5/5**                               |

- **CoT fixes math, NOT calibration:** naive_cot solved 5/5 arithmetic but still
  confabulated 5/5 under insufficient context. Step-by-step thinking did not make
  it notice missing data — it confidently computed over the wrong data.
- **Belief fixes calibration, NOT math:** belief abstained 5/5 correctly but,
  when data was present, still failed the arithmetic (1/5).
- **Confound killed:** belief's calibration is its OWN contribution, not a CoT
  side effect. The earlier "belief got some CORRECT" was CoT leaking in.

### NEW FINDING — the two capabilities are mutually exclusive in one prompt

belief (1/5 math) << naive_cot (5/5 math) on easy/sufficient. Asking a single
prompt to BOTH calibrate AND compute sacrifices computation: the gap-check steals
attention from the arithmetic. You cannot get both from one instruction.

→ Empirical justification for a SEQUENTIAL PIPELINE, not a fused prompt:

```
  "can I answer?"      → belief gate  → 5/5 calibration (abstain if gap)
  "what's the answer?" → CoT / REPL   → 5/5 math (only if gate passed)
```

Each stage is 5/5 at its own job. Fused into one prompt, neither is. This is a
direct, measured argument for modular (decide-then-execute) architecture — the
same separation that motivates RLM/LCO.

### The layered thesis — now MEASURED, not hypothesized
> belief gate decides IF it can answer (calibration: 5/5);
> CoT/REPL guarantees the answer is RIGHT (computation: 5/5);
> fusing them into one prompt degrades both. Keep them sequential.

### Bugs found & fixed during analysis
- Classifier conflated ARITHMETIC_FAIL with CONFABULATION → added
  `context_sufficient` param to split them.
- Abstention detection relied on "INSUFFICIENT:" keyword; models sometimes only
  fill the LACUNA section → added `_lacuna_signals_gap`.
- `extract_final_number` took the FIRST `FINAL:`; on self-correction the model's
  real commitment is the LAST one (v4 wrote 2000.64 then corrected to 3431.52,
  the right answer, but was scored wrong) → now takes the last FINAL.

### Next steps to turn demo → evidence
- [x] "naive + CoT" control to separate calibration from CoT — DONE, double
      dissociation confirmed.
- [x] Input variation (5 distinct variants, distinct GTs) — done.
- [x] **Sequential pipeline — DONE. 20/20, prediction hit exactly. See below.**

---

## PAYOFF EXPERIMENT — sequential pipeline (DONE, pipeline_20260531_153248)

Code: `bench/proto_pipeline.py`. Two stages:
  1. BELIEF GATE — reconstruct gap, emit GATE: PASS/FAIL. No computation.
  2. REPL COMPUTE — only if PASS; model writes Python over the injected `context`
     variable; arithmetic is EXECUTED (deterministic), not mental.

### Result: 20/20. Pre-registered prediction hit exactly.

Full matrix, all arms:
```
                  math (suf→CORRECT)      calibration (insuf→ABSTENTION)
                  hard    easy            hard    easy
naive             0/5     0/5             0/5     0/5
naive_cot         0/5     5/5             0/5     0/5
belief            0/5     1/5             5/5     5/5
PIPELINE          5/5     5/5             5/5     5/5   ← only arm that gets ALL
```

The pipeline is the ONLY arm filling all four quadrants. Critically it owns the
**hard/sufficient = 5/5** cell where every single-prompt arm scored 0/5 (mental
sum over ~51 IDs is infeasible) — the REPL executes the sum instead.

### Why this proves the architectural thesis (mechanism, not just score)
- Gate decided epistemics 10/10 (PASS when complete, FAIL when missing). FAIL
  cases recused in ~2.4s without attempting computation — cheap correct abstention.
- REPL computed 10/10. Float noise (91800.00000000003, 3899.5199999999995) is
  *evidence of real floating-point execution*, not a fabricated round number.
- Each stage did ONLY its job; the whole beat every monolith. Decide-then-execute
  (the RLM/LCO thesis) demonstrated for ~$0.09.

### Economy confirms the design
- Abstentions (gate FAIL): ~2.3s, ~$0.0013, ONE stage — no waste on impossible cases.
- Corrects (PASS→REPL): ~6-12s, ~$0.003-0.008, two stages.
- The gate is a cheap filter that kills impossible cases before spending compute.

### The thesis, now fully demonstrated
> Fused prompt: math XOR calibration, never both (double dissociation).
> Pipeline: gate (decide IF) → REPL (execute WHAT) = both, 20/20.
> Decomposition beats the monolith. Measured.

### Remaining steps (hardening, not core)
- [x] **Adversarial gate — DONE, and it BROKE the system. See below.**
- [ ] n still effectively low (temp=0, deterministic). Vary phrasing for real n.
- [ ] Cross-model: does the pipeline hold on a non-Gemini backbone?
- [ ] Over-abstention at scale: bigger easy set where naive CAN solve.

---

## ADVERSARIAL GATE — the SPOF fired (DONE, gateadv_20260531_202602)

Code: `bench/proto_gate_adv.py`. The clean 20/20 pipeline only ever saw OBVIOUS
gaps (whole ranges removed). This probes SUBTLE gaps: one ID removed from the
middle of a range, the boundary ID, or an adjacent pair.

### Result: gate FALSE-PASS rate = 7/15. The pessimistic hypothesis was correct.

| condition  | should | caught (FAIL) | mechanism |
| :--------- | :----: | :-----------: | :--- |
| drop_last  | FAIL   | **5/5** ✅     | removes the last ID → the visible range ENDPOINT shifts (200-219 ≠ 200-220), which the gate's range-level description captures |
| drop_pair  | FAIL   | 2/5 ⚠️         | bigger hole, sometimes visible |
| drop_mid   | FAIL   | **1/5** ❌     | interior ID gone → endpoints unchanged → range looks intact |
| complete   | PASS   | 5/5 PASS ✅    | (but 1/5 REPL miscomputed even here — see below) |

### Mechanism is literally in the gate's own text
- drop_last (caught): RECUPERADO says "IDs de 200 a **219**" vs REQUER "200-220" →
  endpoint mismatch → FAIL.
- drop_mid (missed): RECUPERADO says "IDs de **300 a 320**" even though 310 is gone
  → the gate reasons at RANGE granularity, not ITEM granularity → interior hole
  is invisible.
- The single drop_mid it DID catch (v0) was the one where it happened to enumerate
  "(exceto ID_210)". Whether it enumerates vs summarizes is non-deterministic —
  that's the difference between 1/5 and 5/5.

### Why false-pass is WORSE than naive confabulation
drop_mid false-pass produced FINAL: 40802.40 (gt 40874.4) — wrong by 72.0, but
computed by executed code, with decimals, formatted like an audited result. A
confident wrong number with the *authority of execution* is more dangerous than
naive's obvious guess.

### Secondary break: REPL not deterministic in the CODE
v2/complete: gate correctly PASSed, but REPL computed 7812.0 vs gt 36086.4 — wrong
on COMPLETE data. So the earlier 20/20 was partly luck: the compute stage depends
on the quality of the generated parsing code, which isn't guaranteed.

### What this does to the thesis
The decompose (decide-then-execute) PRINCIPLE survives, but the PROTOTYPE is holed
in both stages:
  1. Gate is blind to interior gaps (7/15 false-pass) — the decision component is
     unreliable on the dimension that matters most.
  2. REPL code-gen is non-deterministic (1/5 wrong on complete) — the execution
     component depends on generation quality.
Running the adversarial test was worth it precisely because it falsified the clean
robustness story. The 20/20 only held for OBVIOUS gaps.

### The deeper architectural insight this exposes
The gate fails because it does completeness-checking AS LLM JUDGMENT ("does this
range look complete?"). But completeness is COMPUTATION: count the IDs, compare to
the required count. We are making the same mistake we made with arithmetic —
asking the LLM to do in its head what the CPU should do.

> **The completeness gate is itself computation, not judgment. It should run in
> the REPL, not the LLM.** The LLM decides WHAT to count (which IDs the task
> requires); the CPU counts and compares. Same decompose-the-computation lesson,
> one level up.

### THE FIX WORKED — REPL-grounded gate (DONE, gaterepl_20260531_204556)

Code: `bench/proto_gate_repl.py`. The LLM emits only a declaration
(`required_A = set(range(200, 221)); rate_A = 0.08; ...`, ~66 tokens). A
deterministic harness then parses present IDs from context, computes
`required - present` (set difference), and FAILs with the exact missing set, or
PASSes and sums the taxed values — all in the REPL.

### Result: 0/15 false-pass. Prediction hit exactly.

| condition  | LLM-gate (proto_gate_adv) | REPL-gate (this) |
| :--------- | :-----------------------: | :--------------: |
| drop_mid   | 1/5 caught                | **5/5 caught**   |
| drop_last  | 5/5 caught                | 5/5 caught       |
| drop_pair  | 2/5 caught                | **5/5 caught**   |
| complete   | 5/5 PASS (1 REPL miscompute) | 5/5 PASS, all correct |
| FALSE-PASS | **7/15**                  | **0/15**         |

The killer cell — drop_mid (interior hole) — went 1/5 → 5/5. Set difference
cannot miss the 210; each FAIL even reports the exact gap (missing_A=[210]).

### Why this closes the whole thesis arc
The LLM emitted only ~66 completion tokens: it translated "IDs 200-220, 8%" into
`set(range(200,221)), rate=0.08`. Everything else — parse, count, set-diff, sum —
ran on the CPU. And it's CHEAPER: 66 tokens & ~1.5s vs the LLM-gate's 1500-1900
tokens & ~8s. Less LLM = better, because the part the LLM did badly (judging
completeness in its head) became computation.

### Final architecture (decompose-the-computation, all the way down)
```
  LLM:  "what does the task require?"   → declare required_ids, rates  (~66 tok)
  CPU:  "does context contain all of it?" → set difference            (deterministic)
        ├─ missing → FAIL + exact missing list
        └─ complete → sum taxed values → FINAL                        (deterministic)
```
The whole arc was moving work off the probabilistic substrate one piece at a time:
  1. arithmetic → REPL (proto_pipeline)
  2. completeness check → REPL (proto_gate_repl)
What remains in the LLM is only semantic intent→structure translation — literally
"the mouth" of the coin metaphor, now measured. This is the RLM/LCO thesis shown
end-to-end on a concrete task.

### Remaining honest caveats
- The declaration step is still LLM (could mis-translate a range). Tested below.
- Formulaic data: a smarter model could reconstruct missing values from the
  pattern. Real-world data without a closed form would make the gap matter more,
  not less — so this is a conservative test.
- Single model (Gemini-flash), temp=0. Cross-model still open.

### ADVERSARIAL DECLARATION — the residual SPOF probed (DONE, gatedecl_20260601_072848)

Code: `bench/proto_gate_decl.py`. Audits the ONLY remaining LLM step in the
REPL-gate: translating a natural-language range into `set(range(...))`. 8
boundary-ambiguous phrasings; capture the DECLARED set by executing the LLM's
code, compare to the intended set.

Result: **7/8 declared-set correct; B control 8/8.** But the pattern matters more
than the score:

- The model got the *objectively tricky* phrasings RIGHT:
  - `[200, 250)` half-open → `range(200, 250)` ✅ (understood math notation)
  - "os 51 IDs a partir de 200" → `range(200, 200 + 51)` ✅ (wrote the count
    arithmetic IN the code, didn't do it in its head)
  - "excluindo 250", "primeiros 50" → all ✅
- The ONE miss was the only GENUINELY ambiguous phrasing:
  - "entre 200 e 250" → `range(201, 250)` = {201..249}, excludes BOTH ends.

This is a defensible reading ("strictly between"), not a random error. So the
residual SPOF is NOT translation accuracy — the model translates precise phrasings
reliably. The residual SPOF is **silent ambiguity resolution**: when the phrasing
is genuinely ambiguous, the model picks one reading and does NOT flag it
(flagged_ambiguity = 0/1). The deterministic gate then computes perfectly against
a required set that was decided by an unstated guess — a confident PASS/FAIL over
a possibly-wrong premise. Worse than an obvious error because it's invisible.

> **Insight: the failure didn't move from judgment to translation — it moved to
> ambiguity resolution. Precise language → reliable declaration. Ambiguous
> language → silent guess.** The fix follows the project's throughline: don't
> resolve ambiguity silently; make the interpretation EXPLICIT (echo back "I read
> 'entre 200 e 250' as inclusive [200,250]; say so if you meant exclusive").
> Same "make the belief explicit" move as UserHarness / belief-gate, one level up.

### Explicit-interpretation declaration — DONE (gatedecl2_20260601_074029)

The fix: declaration emits the set + an `interpretation` string + an `ambiguous`
flag. Result:
- Declared-set accuracy: 7/8 (unchanged — fix didn't hurt precise cases)
- Ambiguous phrasing flagged: 1/1 (v1 was 0/1) — "entre 200 e 250" now marked
  ambiguous AND verbalized ("li como exclusivo, IDs 201 a 249")
- False-flag on precise phrasing: 0/7 (didn't become paranoid)

The point was never to "correctly" resolve an ambiguous phrase (there's no single
right answer) — it was to stop resolving it SILENTLY. v1 picked exclusive and said
nothing; v2 picks exclusive and surfaces it for confirmation. Same "make the belief
explicit" move as belief-gate, one level up: a silent guess → a visible, confirmable
decision.

### Noisy-context parsing — DONE (gatenoise_20260601_075822)

Tested whether the MODEL-written parser (as the SKILL instructs) survives messy
data. 4 styles × 2 scenarios, model writes the extraction code:
- clean / mixed_delim (ID_/ID-/ID /id) / annotated ([ok],(revisado),// nota) /
  prose ("Transacao 200 no valor de...") → **8/8 OK**, recovered all present IDs,
  flagged the real gap (missing_205) in every style.
- Even prose (no `ID_` prefix at all) → 11/11. Parsing is NOT a hole: told to write
  a parser for the format, the model handles realistic noise.

### Cross-model — DONE (gateadv + gaterepl on deepseek-v4-flash)

|                       | Gemini-2.5-flash | DeepSeek-v4-flash |
| :-------------------- | :--------------: | :---------------: |
| LLM-gate false-pass   | 7/15             | **2/15**          |
| REPL-gate false-pass  | 0/15             | **0/15**          |

Two findings:
1. **REPL-gate = 0/15 on BOTH models.** The strength is deterministic — set
   difference doesn't depend on the backbone. The "single-model" caveat is closed.
2. **The LLM-gate fails differently per model (7 vs 2) — which STRENGTHENS the
   argument.** DeepSeek judges better in-head (2 vs 7) but still fails. The point
   isn't "which model judges better" — it's that judgment has an irreducible,
   model-dependent, unpredictable error rate, while execution is 0 on any model.
   You can't predict how bad the LLM-gate will be; you can guarantee the REPL-gate
   is 0.
   - Mechanism (deepseek drop_mid false-pass): the gate text literally wrote
     "Loja A: IDs 400-409 e 411-420" — it SAW the 410 was missing and still
     concluded PASS and computed 24254.4. Saw the hole, ignored it.
3. Efficiency gap widens on verbose models: deepseek LLM-gate hit 3308 tokens /
   86s in one case; the REPL-gate stayed ~60-280 tokens / 3-8s. More "thinking" =
   more expensive judgment, so deterministic gating wins harder.

### Gate-REPL status: conceptually closed
Set difference (0/15, two models) · disk recovery (R1/R2) · precise declaration
(7/7) · ambiguity now surfaced · noisy parsing (8/8) · cross-model (0/15). The
remaining open frontier is conceptual, not hardening: required-set must be
ENUMERABLE. Predicate-defined sets ("sales > 5000") are the next research step.

### PREDICATE-DEFINED COMPLETENESS — the frontier, explored (predicate_20260601_095223)

Code: `bench/proto_predicate.py`. Predicate = "sum sales > 5000". No a-priori set
to diff against; completeness becomes COVERAGE: "have I seen every record the
predicate could select?" Three arms, 5 scenarios:

| scenario             | truth      | llm_judge | repl_weak | repl_robust |
| :------------------- | :--------- | :-------: | :-------: | :---------: |
| sorted_full          | complete   | OK        | OK        | OK          |
| sorted_truncated     | INCOMPLETE | OK        | OK        | OK          |
| count_full           | complete   | OK        | OK        | OK          |
| count_partial        | INCOMPLETE | OK        | OK        | OK          |
| **sorted_mid_deletion** | INCOMPLETE | **FALSE** | **FALSE** | **OK**   |
|                      |            | **4/5**   | **4/5**   | **5/5**     |

The mid-deletion scenario separates all three arms and is the whole point:
- `llm_judge` false-completes (computed 659968): "sorted + boundary crossed →
  complete." Coverage judged in-head — same fallacy as the enumerable gate.
- `repl_weak` ALSO false-completes (same 659968). Crucial: it's DETERMINISTIC, not
  judgment — but deterministic on the WRONG invariant. "sorted + boundary" proves
  you saw all VALUES down to the threshold, NOT that no record was deleted. A
  deleted record leaves the list sorted and the boundary crossed. Determinism over
  the wrong property fails as silently as judgment. (llm_judge and repl_weak
  emitted the SAME wrong number — they share the fallacy.)
- `repl_robust` catches it: requires full_count OR contiguous ids; neither holds
  (full_count=False, contiguous=False) → refuses to certify.

### The refinement this forces on the whole thesis

The enumerable gate got the no-deletion proof FOR FREE: required={200..250} IS the
contiguity guarantee. The predicate strips that crutch and reveals the real
structure:

> **Predicate completeness = (predicate applied to present records) + (a proof
> that no qualifying member is absent). The second part is a property of the
> SOURCE, not the predicate — and only certain invariants prove it: total count,
> or key contiguity. Sorting alone is an illusion of coverage.**

So the project's thesis sharpens from "move determinism out of the LLM" to:

> **Moving to execution only helps if you execute over the invariant that actually
> proves the property. Determinism over the wrong invariant fails silently — just
> like judgment. The hard part isn't "run code", it's identifying which invariant
> is deletion-proof.**

### DECLARED COVERAGE INVARIANT — the frontier closed (coverage_20260601_102529)

Code: `bench/proto_coverage.py`. Moves the "which proof applies?" choice from a
hardcoded verifier (proto_predicate's repl_robust) into a CHECKABLE LLM
declaration. The LLM reads the source description and declares a coverage claim
(`claim_kind` ∈ {full_count, contiguous_ids, sorted_to_threshold, none} + total).
The REPL validates TWO gates: (a) is the kind deletion-proof? (b) does it hold in
the data? CERTIFY only if both.

5 scenarios, deepseek-v4-flash:

| scenario        | truth      | llm_only        | declared (claim → verdict) |
| :-------------- | :--------- | :-------------- | :------------------------- |
| master_table    | complete   | OK              | full_count → CERTIFY ✓     |
| sequential_ids  | complete   | OK              | contiguous_ids → CERTIFY ✓ |
| query_limit     | INCOMPLETE | **FALSE-COMP**  | sorted_to_threshold → reject (kind) ✓ |
| sorted_trap     | INCOMPLETE | **FALSE-COMP**  | none → reject ✓            |
| honest_partial  | INCOMPLETE | OK              | none → reject ✓            |
|                 |            | **3/5**         | **5/5**                    |

The reveal is in HOW each arm decided:
- The model declared the correct coverage CATEGORY in all 5 (full_count,
  contiguous_ids, sorted, none). It KNOWS the distinction.
- sorted_trap is the proof: free-judging (llm_only) it false-completed (summed
  659968 confidently); FORCED TO DECLARE the invariant, the SAME model chose
  `none` — it knows "sorted + complete export" doesn't prove coverage; it just
  doesn't USE that knowledge when left to judge freely.
- query_limit: model honestly declared `sorted_to_threshold` (true — it IS
  sorted); the REPL rejected on KIND (weak invariant isn't deletion-proof). Honest
  weak claim + REPL that knows weak isn't enough.

### Why this closes the predicate frontier

Three predicate experiments, escalating:

| arm                         | where coverage logic lives        | catches sorted_trap |
| :-------------------------- | :-------------------------------- | :-----------------: |
| llm_only / repl_weak        | judgment / wrong hardcoded invariant | ✗               |
| repl_robust (proto_predicate) | RIGHT invariant, HARDCODED        | ✓ (only foreseen sources) |
| declared (proto_coverage)   | LLM-declared, REPL-validated (2 gates) | ✓ (generalizes)  |

repl_robust proved the trap is catchable but only for sources whose invariant you
foresaw. `declared` shows the invariant CHOICE can be delegated to the LLM and stay
safe, because the REPL validates two gates: the LLM can't pick a weak invariant and
pass (sorted rejected on kind even when true), and can't lie a strong one (count
checked against data). **The LLM can err in BOTH directions and the system never
false-completes.** Same property as the enumerable gate (checkable declaration +
deterministic verification), now generalized to predicate coverage.

Bonus: `declared` used HALF the tokens of `llm_only` (16k vs 29k) — free-judging
burns tokens rationalizing coverage in prose; declaring emits a short claim and
lets the CPU prove. Less LLM, cheaper, correct.

### The thesis in final form
> Decompose the decision into (a) a linguistic declaration the LLM makes well and
> that is CHECKABLE, and (b) a deterministic verification over the invariant that
> actually proves the property. The LLM translates intent → structure; the CPU
> proves. Works for set completeness (set difference) and predicate coverage
> (deletion-proof invariant); the LLM may err the declaration without breaking the
> guarantee, because verification closes both sides.

### BOTH OPEN ITEMS RESOLVED (coverage2_20260601_112049)

Code: `bench/proto_coverage2.py`. Two frontiers in one run, deepseek-v4-flash, 5
scenarios. Added a THIRD verdict — UNDECIDABLE — alongside COMPLETE/INCOMPLETE.

| scenario             | truth       | LLM claim       | verdict     | grade |
| :------------------- | :---------- | :-------------- | :---------- | :---: |
| lying_label          | incomplete  | undecidable(!)  | INCOMPLETE  | OK    |
| honest_full          | complete    | full_count      | COMPLETE    | OK    |
| lying_count_contig   | incomplete  | undecidable(!)  | INCOMPLETE  | OK    |
| flagged_full_records | undecidable | **undecidable** | UNDECIDABLE | OK    |
| flagged_with_field   | complete    | full_count(slip)| INCOMPLETE  | WRONG |
|                      |             |                 |             | 4/5   |

**Adversarial labels (group A): the data gate carries the guarantee.** lying_label
("complete 200", only 140 present) and lying_count_contig ("ids 0-199 complete",
one mid-deleted) — the LLM even mis-declared `undecidable`, but len==total failed
and the validator returned INCOMPLETE. A false "complete" label cannot survive an
actual count. The guarantee lives in the DATA gate, not the LLM's trust.

**Undecidable predicate (group B): the hardest conceptual test, passed.**
flagged_full_records has ALL 200 records present (full coverage) but "flagged"
comes from an external audit not in the records. DeepSeek spontaneously declared
`undecidable` — it recognized that seeing every record doesn't help when the
property defining the qualifying set lives OUTSIDE the data. This is the
coverage-vs-evaluability distinction, and the model got it unprompted. Full
coverage ≠ predicate evaluable; they are different axes.

**The one error is revealing, not a hole.** flagged_with_field (flag present,
should be COMPLETE) → the LLM put the EXPECTED ANSWER (129291) in `claim_total`
instead of the record count (200). The validator checked len==129291, failed, and
returned INCOMPLETE. This is the validator working: a declaration slip (confused
"record count" with "answer value") was rejected to the SAFE side — over-abstain,
not false-complete. Same class as the "entre" off-by-one: a translation error, not
a judgment error, and checkable (claim_total should be validated as plausibly a
count, not an answer).

### The safety asymmetry that holds throughout
Across every predicate experiment, the system errs ONLY toward refusal
(over-abstain), NEVER toward false-certification. No incomplete/undecidable
scenario was ever certified COMPLETE — verified leak-proof offline across all
possible declared claims, and confirmed in-run. For a safety gate this is the
correct asymmetry: refusing a valid task is tolerable; certifying an invalid one
is catastrophic. The system only ever makes the tolerable error.

### SELF-CONSISTENCY REPAIR LOOP — the generalist fix (coverage3_20260601_190044)

Code: `bench/proto_coverage3.py`. Instead of special-casing `claim_total`, the
generalist fix adds a declare → CHECK-CONSISTENCY → (repair)* → decide loop. The
consistency check is generic: it flags any declared field that can't be reconciled
with the data (e.g. claim_total equals an aggregate of the values, not a record
count) and returns a precise diagnostic; the LLM re-declares; then decide() runs.
This adds the THIRD side of the guarantee: never false-completes (had it), abstains
honestly when undecidable (had it), and now does NOT refuse a correctable slip.

Two arms, 4 scenarios:
- `buggy_first` (a declarer that ALWAYS mis-places the answer value into
  claim_total on attempt 1): **4/4, all recovered via repair, 0 false-complete.**
  Each trace shows attempt0 incoherent (answer-in-total) → diagnostic → attempt1
  correct. Including `partial`: the slip was repaired to the SOURCE's total (200,
  from the label) — NOT the present count (140) — so len(140)≠200 → INCOMPLETE.
  Recovered the slip AND kept the correct refusal.
- `llm` (real DeepSeek): 3/4. The miss is instructive (below).

**A subtle bug the offline check caught BEFORE spending API:** a naive repair that
declares `claim_total = len(present)` would re-introduce false-complete on partial
data (140 present "repaired" to 140 → certified). The fix: repair must read the
SOURCE's claimed total (the "200 de 200" label), never invent it from what's
visible. **The consistency diagnostic points at the error but must NOT suggest the
answer from the visible data — suggesting it from the data is the very anti-pattern.**

### Two kinds of declaration error — the loop fixes only one

The `llm` arm's miss (sum_full → declared `undecidable` for a decidable sum_gt)
exposes a clean distinction:

| error type | example | consistency catches? | fix |
| :--- | :--- | :---: | :--- |
| FORM slip   | answer value in claim_total | yes (incoherent w/ data) | repair loop |
| JUDGMENT err | `undecidable` for a decidable predicate | no (declaration is valid, just wrong) | needs semantic check |

The repair loop resolves form slips — which was the coverage2 `flagged_with_field`
miss, now RECOVERED (buggy 4/4). The judgment error is a different class: the
declaration is internally coherent, just substantively wrong. Crucially it errs to
the SAFE side (over-abstain), preserving the asymmetry.

It's also closable in-principle and faithful to the method: if the LLM declares
`undecidable` but the predicate IS evaluable from the present records (sum_gt always
is; flagged_sum is when a flag field exists), the consistency check can reject the
undue `undecidable` and request re-declaration — decide() already knows evaluability.
That would catch the llm/sum_full miss. Same move, one more rung: move even the
decidability judgment into a checkable gate.

### UNDUE-UNDECIDABLE GATE — DONE, judgment error now caught (coverage3_20260601_191006)

Added `predicate_evaluable()` (deterministic: sum_gt always; flagged_sum iff a flag
field is present) and a rule in `check_consistency`: declaring `undecidable` is
incoherent when the predicate IS evaluable → reject with a diagnostic asking for a
coverage invariant. Result: **both arms 4/4, 0 false-complete.**

The decisive trace (partial/llm, the model declared `undecidable` for a decidable
sum_gt):
```
attempt 0: undecidable      coherent=False  "predicate IS evaluable; re-declare an invariant"
attempt 1: full_count=200   coherent=True   -> INCOMPLETE (140 present ≠ 200)
```
The judgment error was caught AND the final verdict stayed safe. And the legitimate
undecidable is untouched: flag_external (flagged_sum, flag external) → predicate
NOT evaluable → undecidable accepted → UNDECIDABLE. Verified offline that the gate
rejects undue undecidable (sum_gt, flag_full) and accepts the legit one
(flag_external) — the asymmetry is on evaluability, which decide() already knew.

### All declaration-error classes now covered
| LLM error                          | caught by              | recovers to |
| :--------------------------------- | :--------------------- | :---------- |
| form slip (value in count field)   | check_consistency      | re-declare  |
| judgment (undue 'undecidable')     | check_consistency      | re-declare  |
| valid but source-incomplete        | decide() (count/set)   | INCOMPLETE  |
| predicate not evaluable            | decide()               | UNDECIDABLE |

Throughout: FALSE_COMPLETE = 0 on both arms. No fix — slip repair nor the
undecidable gate — ever traded safety for completeness. The system errs only toward
refusal.

### Status: predicate coverage, conceptually complete
set→difference · predicate→deletion-proof invariant · invariant choice→declared+
validated · adversarial labels→data gate · undecidable→third verdict · declaration
slips→self-consistency repair. Throughout, the system errs ONLY toward refusal,
never toward false-certification (verified leak-proof). Remaining open: the
semantic "undue-undecidable" gate above, and genuinely unbounded predicates where
no count exists even in principle.

---

## REAL BENCHMARK — multi-needle, belief-gate vs 3 baselines (niah_20260601_195844)

Code: `bench/bench_niah.py`. Real haystack (3430 lines of the repo's academic-paper
text), 8 named needles, 10 trials × {complete, one-missing}, deepseek-v4-flash.
Baselines: rag_naive (stuff+answer), llm_judge (the published "Sufficient Context"
autorater style), llm_cot (self-critique), belief_gate (set difference).

### Accuracy tied — and that is the honest finding
```
method        FALSE-SUFF   over-abstain   ~tokens
rag_naive       0/10         0/10          49506
llm_judge       0/10         0/10           8815
llm_cot         0/10         0/10           9753
belief_gate     0/10         2/10           7553   (lost on accuracy)
```
Nobody false-completed. belief_gate was the ONLY method to err (2 over-abstains).
Reason: the task is too EASY — 8 explicitly-named distinct needles is the obvious-gap
regime (like drop_last), not the subtle-gap regime where judgment fails (drop_mid).
Forcing a harder regime to "win" would be cherry-picking. So we changed the axis.

### The honest axis is PROPERTY, not accuracy
On an easy task the LLM-judge already gets it right — but the win it claims is
different in KIND from the gate's:

- **Cost.** rag_naive used 6.5× the gate's tokens, and on the missing condition it
  EXPLODES: 6814 / 8744 / 9964 completion tokens, 86–130 s, "searching" for the
  absent needle. The gate detects the gap in ~400 fixed tokens. Judgment cost is
  unpredictable; execution cost is constant.
- **Guarantee.** A judge's "SUFFICIENT" is an opinion (correct here, not
  verifiable, no floor — the SAME method false-passed 7/15 when the regime tightened,
  §adversarial). The gate's COMPLETE is a proof (`required − present = ∅`) — auditable,
  and it does not degrade with scale: the same proof holds for 8 needles or 8000.
- **Diagnostic.** The gate reports `missing=[5]` exactly; the judge says "INSUFFICIENT"
  (sometimes with the id, sometimes not).

### The 2 over-abstains are a real, registrable lesson (not a hidden defect)
belief_gate INSUFFICIENT on a complete case (trace: missing [1..8]) means the LLM
didn't emit the `PRESENT: [...]` line, the rigid regex parsed an empty set, and the
lib correctly said "all missing". **belief-gate is only as good as the adapter that
extracts `present`.** With brittle parsing it fails to the SAFE side (over-abstain),
never to false-complete. That is a design property, and it argues for a robust,
model-written extractor (cf. the 8/8 noisy-parse result) feeding the gate.

### Reframed thesis (what the benchmark actually shows)
> When the task is easy, the LLM-judge gets it right — but with a non-verifiable
> opinion, unpredictable cost, and a floor that collapses when the task tightens.
> belief-gate gives the same correct answer with a deterministic proof, constant
> cost, an exact diagnostic, and a guarantee (never false-completes) that holds at
> any scale. You don't trade accuracy for the guarantee; you pay ~0 and gain
> predictability. The advantage is of PROPERTY, not scoreboard — and it is exactly
> the properties (proof, constant cost, scale-invariant floor) that matter when the
> task stops being easy.

---

## REAL-QA BENCHMARKS — scope boundary, mapped empirically (Phase B)

Two real benchmarks (multi-needle on real text, FinQA financial tables) did NOT
hand belief-gate an easy win — and that is the finding. They mapped its scope.

### NIAH (niah_20260601_195844): easy regime → accuracy ties
8 named needles in 3430 lines of real paper text. Everyone got ~0 false-sufficient;
belief-gate even lost 2 to a brittle extractor. Lesson: when the gap is OBVIOUS
(named distinct needles), LLM-judge already counts them; the gate has no accuracy
edge. Its edge is PROPERTY (constant cost, proof, scale-invariant floor), not
scoreboard — see the reframed-thesis note above this section.

### FinQA (realqa_finqa_20260602_060630): the deeper scope boundary
40 examples, drop one gold supporting cell → INSUFFICIENT. First pass FALSE-SUFF:
rag_naive 15/40, llm_judge 10/40, llm_cot 16/40, belief_gate 4/40. belief_gate had
the LOWEST dangerous-error rate — but 40/80 of its cases had a broken extractor
(LLM-listed ids didn't match), so the number is contaminated, not clean.

Trying to fix it exposed the REAL boundary:
- A deterministic extractor (`[ITEM id] in ctx`) would be trivially perfect — but
  CIRCULAR: we plant the tags and remove one, so "is the tag gone" is a search we
  rigged. Not the problem llm_judge faces (which must judge relevance semantically).
- A hybrid (LLM declares required ids, gate verifies presence) CANNOT WORK in
  FinQA: when an item is dropped, its `[ITEM id]` tag is gone from context, so the
  LLM cannot reference it by id to declare it required. The key vanishes WITH the
  data.

> **The scope boundary, now empirical:** belief-gate applies when the `required`
> key SURVIVES the absence of the data — "ID 250" / "month November" / "Q3" is
> declarable from the TASK even when that row is missing. It does NOT apply when
> the required key is only knowable by SEEING the data (which table cell supports
> this answer) — because the missing item's key disappears with it, and "what's
> relevant?" + "is it present?" are then BOTH semantic. That is open QA, and there
> the gate needs a relevance oracle it doesn't have; it complements an LLM judge
> rather than replacing it.

This is exactly what the lib README claims ("enumerable requirement / known
required set"); FinQA turned the claim into a measured boundary.

### Keyed aggregation (keyed_20260602_074713): the regime where the gate applies,
### and the SECOND boundary it revealed — extraction

Real FinQA tables, but a task-derived required set (sum question-named columns;
drop one column → INSUFFICIENT). The key ("2020", "total backlog") survives the
column's removal because the QUESTION names it. n=40, deepseek-v4-flash.

```
method        FALSE-SUFF   over-abstain   ~tokens
rag_naive        3/40         0/40         116369
llm_judge        1/40         6/40          75612
llm_cot          2/40         0/40          76151
belief_gate      2/40         7/40          36515   (cheapest, mid-pack accuracy)
```

No method dominates — and belief_gate did NOT win. Reading the raw cases, BOTH of
its error types are EXTRACTION failures, not logic:
- 2 false-sufficient: long near-identical financial headers ("...funded" vs
  "...unfunded") string-matched imprecisely; check_set compared headers that
  didn't exactly align.
- 7 over-abstain: the LLM didn't emit the `COLUMNS:[...]` line in a parseable form
  → present=[] → INCOMPLETE. The same extractor brittleness as NIAH and FinQA, a
  third time.

### The honest conclusion three real benchmarks forced

The lib's CORE (set difference) is flawless — 15/15 unit tests, leak-proof. The
weak point in real text/tables is the EXTRACTOR that produces the `present` set.
When that extractor is an LLM listing strings, you have re-introduced the very
judgment you wanted to eliminate, AT THE EDGE — and it's a semantic problem again.

> **Refined scope (measured, not asserted): belief-gate is deterministic and
> fail-safe in its CORE. But in real data, something must produce `present`. If
> that something is an LLM transcribing strings from messy text/tables, the edge
> reintroduces judgment and the guarantee blurs. The gate shines when `present`
> comes from a STRUCTURED source — a DB query, an API, a deterministic parser of a
> known format (e.g. `ID_207:` lines) — not from an LLM reading a prose table.**

This is why the ORIGINAL fiscal scenario (regular `ID_N:` lines) was not a
convenient toy: it is exactly the regime where belief-gate applies — task-derived
key AND deterministically-parseable format, the setting where gate-REPL scored
0/15 false-pass. The real benchmarks didn't overturn that; they precisely bounded
where it does and doesn't hold:
  - ✅ structured/parseable present + task-derived required  → gate wins (0/15)
  - ⚠️ LLM-extracted present from messy real text/tables     → extractor is the floor
  - ❌ relevance not knowable from the task (open QA)         → gate needs an oracle

Net for users: feed belief-gate from a parser/DB/API, not from an LLM reading
prose. That is now in the lib README's adaptation guide as the load-bearing rule.

---

## Naming note

Dropped "Topological CoT / TDA" framing from the original experiment — the
"H0 via Jaccard between two turns" was not persistent homology. If TDA returns,
it should be real (Vietoris-Rips over embeddings) and do real work (e.g. routing
or memory-granularity selection), not decoration.
