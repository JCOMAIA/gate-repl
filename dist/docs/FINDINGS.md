# belief-gate / gate-REPL — consolidated findings

Every measured result of the program, in one honest place. Each row is reproducible
from a `bench/` harness; the deeper method write-ups are `docs/GATE_REPL.md` (evidence),
`docs/UNIFICATION.md` (the principle), and `IDEAS.md` (the full lab notebook).

## Thesis

Move determinism *out* of the LLM, one step at a time — arithmetic, completeness
checking, boundary interpretation, the coverage proof itself. What remains is the
irreducible, *checkable* linguistic core: translate intent into a structure the CPU
can verify. The result errs only toward honest refusal, never toward a confident wrong
answer — and it does so cheaper, faster, and model-independently.

The single dividing line the whole program turns on:

> Determinism is achievable exactly where the required/verified set is **enumerable**
> (presence, ranges, counts, coherence fingerprints). Where the property is an **open
> class** (modality, relevance, meaning), you get at most provenance or a structured
> slot — never closed-set CPU verification.

## The measured results

### 1. The single point of failure, and its fix
An LLM asked "is this context complete?" **false-passes on subtle interior gaps** —
7/15 (gemini), 2/15 (deepseek). Move the check into executed code (LLM declares the
*required* set; CPU computes `required − present`) → **0/15 on both models**. The gate
never certifies an answer it cannot prove complete. *(`bench/proto_gate_adv.py`,
`proto_gate_repl.py`.)*

### 2. The core is leak-proof, exhaustively
The set/coverage/memory core has **25/25 unit tests** (leak-proof: never false-completes).
On real FinQA tables the deterministic gate was tested **exhaustively** — every 3-column
task-subset of every usable table, **9,580 decisions, 0 errors**. The 0/0 is structural,
not a lucky sample. *(`beliefgate/tests/`, offline power sweep.)*

### 3. Cross-model: the deterministic gate is the only method clean on every model
Keyed aggregation (sum task-named columns; drop one → must abstain), pooled over
deepseek-v4-flash ×2 + gemini-2.5-flash (120 decisions/condition):

| method | dangerous (false-sufficient) | false-alarm (over-abstain) | tokens |
| :--- | :--- | :--- | :--- |
| rag_naive | 16/120 | 1/120 | 85,348 |
| llm_judge | 2/120 | 30/120 | 58,471 (+22 unparseable) |
| llm_cot | 3/120 | 1/120 | 111,927 (+22 unparseable) |
| belief_gate (LLM-extract) | 0/120 | 39/120 | 40,247 |
| **belief_gate_det** | **0/120** | **0/120** | **0** |

The single-model "tie" with `rag_naive` (0/0 on one deepseek draw) **dissolved on a
second model**: gemini's `rag_naive` confabulated a wrong total **35% (14/40)** of the
time. `belief_gate_det` is the only method that is 0-dangerous + 0-false-alarm +
0-cost + bit-reproducible on *every* model. *(`bench/realqa/harness_keyed.py`.)*

### 4. End-to-end: LLM → gate → REPL → answer is correct-or-abstains (the double dissociation)
Measuring the full system producing the *answer*, pooled over 2 models, 80 cases:

| arm | COMPLETE correct | INSUFFICIENT abstain | dangerous confab |
| :--- | :--- | :--- | :--- |
| llm_direct | 3/80 | 77/80 | 3 |
| gate + llm_compute | 6/80 | 80/80 | 0 |
| **gate + repl** | **80/80** | **80/80** | **0** |

- the **gate** removes the dangerous confabulation (→0) but not the arithmetic error;
- the **REPL** removes the arithmetic error (→80/80) and inherits the gate's abstention;
- only the **full pipeline** is clean on both axes.

The arithmetic axis is brutal for the LLM: **gemini scored 0/40** on COMPLETE (every
multi-cell sum wrong — gold 3,151,435 → "2,600,000"). This is the project's origin
dissociation (CoT fixes arithmetic; belief fixes calibration) in its *deterministic*
form, and the deterministic versions dominate. *(`bench/realqa/harness_pipeline.py`.)*

### 5. Coherence over time: bookkeeping memory (the "arrow with teeth")
A derived value (a cached sum, a remembered fact) is trustworthy only if it carries a
deterministic verifier back to its source. `remember(value, source)` binds it to a
fingerprint; `verify_fresh` returns COMPLETE only if the source is unchanged, names the
exact added/removed/changed keys otherwise, and **UNDECIDABLE when no source is given**
(refuses to certify rather than guess). In a 2,000-trial demo a naive cache served stale
values **59.9%** of the time; the bookkeeping reader served **0** — it proves freshness
or re-derives. *(`beliefgate/memory.py`, `bench/memory/demo_coherence.py`.)*

## The boundary — measured, not asserted (where it does NOT help)

### 6. Single-fact extractive lookup: models self-abstain (gate unnecessary)
Post-answer grounding guardrail on "what is cell X?" with an abstention option. Across
deepseek + gemini-3.1-flash-lite, real-value confabulation was **0** — both abstained
correctly when the cell was blanked; gemini-3.1 was perfect (40/40 + 40/40). The
guardrail is a solution looking for a problem here. Confident confabulation is
**regime-dependent**: it appears in compute/aggregate framing (35% above), not in
single-fact lookup. *(`bench/openqa/harness_claimgate.py`.)*

### 7. Modality: span-anchoring buys provenance, not CPU teeth
A reviewer (cache-coherence / InsightMemoria) proposed giving the modality tag the
gate's teeth by anchoring each tag to the source span that licenses it. Across 3 models,
90 items: **localization works** (99% span fidelity — the model reliably points at the
licensing phrase), but **closed-set verification does not** (83% UNVERIFIABLE; a frozen
cue lexicon covers hypothesis 1/30). The reason is fundamental: **modal cues are an open
class** ("decided" = "fechamos" / "batemos o martelo" / "tá fechado" / …), so the
cue→class step cannot be a closed-set membership test the way presence can. Modality gets
**human/strong-model-auditable provenance**, not CPU-deterministic teeth. *(`bench/modality/harness_span.py`.)*

## The map

| Regime | Who answers | Measured outcome |
| :--- | :--- | :--- |
| **Computable** (aggregation/arithmetic over structure) | LLM → gate → REPL | **correct-or-abstains on both axes** ✅ |
| Single-fact lookup w/ abstention | LLM alone | already well-calibrated; gate adds little |
| Open / semantic QA | LLM (gate as guardrail at most) | no deterministic anchor |
| Modality / "could vs did" | structured slot + span | provenance teeth, not CPU (open class) |

The "arrow with teeth", graded: **CPU-hard** for presence / coverage / coherence
(closed, enumerable); **provenance-only** for modality (open class). The library realizes
the first three in code; the fourth is bounded by the nature of language.

## What's built

`beliefgate/` — zero-dependency library, 25/25 leak-proof tests:
`check_set` (enumerable completeness), `verify_coverage` + a deletion-proof invariant
model and an LLM-declaration repair loop (predicate coverage), `remember`/`verify_fresh`/
`recall` (bookkeeping memory). Integration guide: `beliefgate/INTEGRATION.md`. Real-world
scenarios: `docs/SCENARIOS.md`. Claude Code skill: `plugins/belief-gate/`.

## Honest limitations

- **The extractor is the floor.** When `present` must be read from messy prose by an LLM,
  the gate inherits that LLM's transcription errors. Feed `present` from a parser/DB/API.
- **gate+repl on COMPLETE is correct-by-construction** (it computes the same gold); the
  non-trivial finding is that the LLM arms sit at 3–6/80, i.e. the LLM is the wrong tool
  for exact arithmetic — not that the gate "won a fair fight".
- **n is modest** (30–120 per cell). Adequate to separate 0% from 35%/83%; not to resolve
  small differences. The dramatic results are clean; we don't over-read the rest.
- **The compute-regime tasks are arithmetic-heavy on purpose.** For single-fact lookup the
  LLM is fine and the pipeline adds little — stated, not hidden.
- **Modality verification stays soft** by the open-class argument; we did NOT tune the
  lexicon to manufacture a win (that was the circularity the reviewer flagged).
