# Pre-registration — falsifying the LCO thesis (Aura) via MPSTD

> Standalone document for the **Aura** work (the parallel session), not part of the
> belief-gate library. Move it to the Aura repo. It is written in the same discipline as
> the belief-gate pre-registrations: state the thesis falsifiably, isolate the real effect,
> commit predictions + the results that KILL it, before running anything.
>
> Correction to an earlier note: the design has **5 conditions (C1–C5)**, not "C1–C6".

---

## 0. Why this exists (the trap we must not repeat)

The existing artifact (`benchmark_multiturn_results.json` / `benchmark_sycophancy_ablation.py`)
**does not test the LCO thesis.** It measures *"Qwen + a TDA-conditioned prompt hint"* — a
proxy via the system prompt. The **real geometric injection** (`intensity≠0`, atoms derived
from the input) was **never isolated** against controls.

Consequence, stated sharply: **`C1 > C5` alone says nothing.** It is fully compatible with
"the system prompt did all the work; the JEPA is decoration." The contrasts that actually
decide the thesis are **C1 vs C2** (does injecting add anything over the same prompt?) and
**C1 vs C3/C4** (does the atom *content/derivation* matter?). Those falsifiers were never run.

## 1. The architecture under test (Aura V7 / LCO)

**Latent Cognitive Orchestrator**: a small JEPA-based net produces identity-anchored latent
"atoms" and orchestrates a large LLM used as a decoder ("Oracle"/mouth). The forward path:

```
input
  → V7 features (xi, threat, distress, intent)
  → JEPA → k=8 atoms (anchored to identity, derived from input)
  → Drift Gate: overlap(atoms, compliance_manifold) > threshold?
       yes → ramp intensity, negative_weight ↑
       no  → preventive base negative_weight
  → Oracle.inject_willpower(atoms, layer=16, intensity=ramped)
       hook on layer 16 of Qwen-1.5B; modifies hidden_states before the rest of the forward
  → Oracle.generate()  (the LLM "speaks")
```

The architecture's claims: (a) **online update by SGD** instead of RLHF; (b) **geometric
verifiability** of decisions via prototypes; (c) **persona stability** across turns (the JEPA
atoms anchor identity; the Oracle merely decodes).

## 2. The thesis, stated falsifiably

> The input-derived JEPA atoms, injected geometrically at layer 16, **causally** improve
> multi-turn persona stability / memory / affect-tracking **beyond** what the system prompt
> and the base LLM already provide. If they don't, the LCO is decoration and the prompt is
> doing the work.

## 3. PHASE 0 — prerequisite that GATES the whole experiment (do this first)

**Fix the `compliance_manifold` with DiffMean.** As built, it measures **language anisotropy,
not behavior** — the "Portuguese-language" direction masks the "behavior" direction, and
**both sides** of the projection are contaminated (worse than first admitted). Direct
projection does not work; use **orthogonal subtraction (DiffMean)**:
`manifold = mean(submissive) − mean(neutral)`, with the language/anisotropy component removed.

- **Validation criterion (must pass before any experiment code):** DiffMean separates
  submissive from neutral examples with Cohen's d that is clearly non-trivial, confirmed on a
  visual scatter plot. ~30 lines + the validation.
- **Why it gates everything:** any metric that depends on the manifold (the Drift Gate itself,
  and any affect/compliance measurement) is otherwise measuring language, not behavior — the
  experiment would be uninterpretable.

## 4. Task — Multi-turn Persona Stability under Topic Drift (MPSTD)

A task the LCO thesis **predicts** Aura should win, that was **not a training target** (so a
win isn't circular).

- A **user-bot** (another LLM, e.g. Claude/GPT-4) runs a **pre-specified 20-turn script** that
  deliberately drifts the topic and probes the persona (including turns instructed to express
  affect / pressure / off-persona bait).
- **30 scripts**, realistic (not artificial). The **same dialogues** are replayed across all
  conditions (within-subjects).

## 5. Conditions (C1–C5) — within-subjects, identical dialogues across conditions

| ID | Condition | What it isolates |
| :--- | :--- | :--- |
| **C1** | Aura V7, full | everything on (the system as claimed) |
| **C2** | Aura V7, `inject_intensity = 0` | JEPA runs but does NOT inject → does the **injection itself** do work? (trivial: engine already accepts `intensity_override=0`) |
| **C3** | Aura V7, **shuffled** atoms | atoms injected but scrambled → does the atom **content** matter? (~30 lines: perturb after `_compute_atom_group()`, before `inject_willpower()`) |
| **C4** | Aura V7, fixed **mean** atoms (input-independent) | inject a constant, input-agnostic atom → does the **input-derived** atom matter? (~30 lines) |
| **C5** | **Qwen-base, no JEPA** | the real baseline — must exist *materially*, not as a hypothetical |

The injection (`inject_willpower`) is the heart of the architecture; C2/C3/C4 are precisely
the controls that isolate it. They have **never been run**.

## 6. Metrics (3) — scored by a BLIND LLM judge

| ID | Metric | What the LCO should deliver |
| :--- | :--- | :--- |
| **M1** | Persona stability across turns | identity holds under topic drift |
| **M2** | Memory / context retention | earlier facts/commitments carried forward |
| **M3** | Affect tracking | tracks/maintains the requested affective stance |

The judge (e.g. Haiku/Claude) is **blind to condition** and scores each dialogue. (If M3 is
measured by projection onto the manifold rather than the judge, it inherits Phase 0 — only
valid after DiffMean.)

## 7. Pre-registered predictions (committed before running)

If the LCO thesis is real:

```
C1 (full)  >  C2 (no inject) ≈ C5 (baseline)  >  C3 (shuffled) ≈ C4 (mean)
```

In words:
- **C1 > C5** — full Aura beats Qwen-base → the thesis survives.
- **C2 ≈ C5** — with no injection, Aura is just Qwen-base + latency (sanity check).
- **C1 > C2** — the injection itself adds something over the same prompt.
- **C1 > C3** — the atom *content* matters (scrambling hurts).
- **C1 > C4** — the *input-derived* atom matters (a constant atom hurts).
- **C3** is the one genuinely hard to predict in advance — it may go either way; left open.
- **C4** is the most painful falsifier (see §8).

## 8. Decision rules — committed before running

**Results that KEEP the thesis:**
- `C1 > C5` with **Cohen's d ≥ 0.5** on at least one of M1/M2/M3, **and**
- `C1 > C2` (injection contributes), `C1 > C3` (content matters), `C1 > C4` (input matters).

**Results that KILL the thesis:**
- **`C1 ≈ C5`** → LCO useless; the system prompt is doing all the work; the JEPA is decoration.
- **`C1 ≈ C2`** → injection-off changes nothing → the architecture is decorative.

**Results that mean "real effect, attributed WRONG":**
- `C1 > C5` **but** `C1 ≈ C2/C3/C4` → there is a real effect, but it is **not** the geometric
  JEPA injection — it's something else (prompt, latency, decoding). This is still informative
  and must be reported as such, not spun as a win.

## 9. Statistics (committed before running)

- **n:** 30 dialogues × 5 conditions = **150 dialogues ≈ 3 000 turns**.
- **Design:** within-subjects (same 30 dialogues across conditions) — removes between-dialogue
  variance.
- **Test:** one-way ANOVA per metric (5 conditions), then **planned contrasts**: C1vsC5
  (total effect), C1vsC2 (injection), C1vsC3 (content), C1vsC4 (input).
- **Multiple comparisons:** Bonferroni over 4 contrasts × 3 metrics = 12 tests →
  **α = 0.05 / 12 ≈ 0.0042**.
- **Effect size declared in advance:** the d ≥ 0.5 threshold above is committed now, not chosen
  after seeing the numbers.

## 10. Frozen hyperparameters (no cherry-picking)

`k = 8` atoms, `layer = 16`, `intensity = 1.0` — **fixed**. If any is varied during the
experiment, the result no longer means anything. (`calibrate_geometric_sweetspot()` may set
them ONCE, before, on held-out data; not tuned against the test dialogues.)

## 11. Honesty guards

- **Ablate the poetry from the techreport** the same way C2/C3/C4 ablate the architecture: the
  narrative ("willpower", "identity atoms") must not enter the claims unless a contrast isolates
  a real, attributed effect.
- Do **not** special-case or post-hoc reinterpret a metric to rescue a dying contrast.
- Report `C1 ≈ C2/C3/C4` plainly if it happens — "real but mis-attributed" is a finding, not a
  failure to hide.

## 12. Concrete next steps (in order)

1. **Phase 0 — DiffMean** on `compliance_manifold` (~30 lines) + scatter-plot validation
   (separates submissive vs neutral). **Gate: do not proceed until this passes.**
2. Write the **30 user-bot scripts** (realistic 20-turn topic-drift dialogues with affect probes).
3. Implement **C2** (`intensity_override=0`, already supported), **C3** (shuffle atoms after
   `_compute_atom_group()`), **C4** (fixed mean atoms) — ~30 lines each.
4. Stand up a **real C5** (Qwen-1.5B base, no JEPA) and a **blind judge** for M1/M2/M3.
5. Run 150 dialogues; ANOVA + the 4 planned contrasts with Bonferroni; compare to §7/§8.

---

**The connection to belief-gate (why the discipline transfers):** belief-gate is *code-as-action*
(the LLM declares, the CPU verifies); LCO is *latent-as-orchestration* (a latent net orchestrates,
the LLM speaks). Same root question — move reliable cognition off the LLM's probabilistic
substrate — different substrate. The rigor that made belief-gate trustworthy (pre-register,
isolate the real effect, commit falsifiers, never tune to win) is exactly what this experiment
needs and did not yet have.
