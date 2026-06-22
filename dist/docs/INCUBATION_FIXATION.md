# Fixation and incubation in LLMs

*Does the human "step away and the answer comes" have an AI analogue — and do LLMs even
fixate in the first place?*

A self-contained study. Every number below is reproducible from `bench/incubation/`; the
deterministic parts (item generators, graders) were validated offline before any API spend,
and the negative results are kept as steps rather than hidden.

---

## 1. Where the idea came from

The starting point was a human observation, not a benchmark: *when you're stuck on a
problem, stepping away and doing something else often makes the solution arrive on its own.*
This is the **incubation effect** — real and replicated in psychology.

We asked two things: **(a)** what actually causes it, and **(b)** does anything like it
exist, or could it be introduced, in LLMs? Decomposing the human phenomenon gave three
candidate mechanisms, in decreasing order of empirical support:

1. **Fixation decay (best supported).** Hard focus locks you into a "set" — a region of
   solution space primed by your first (wrong) approach, which keeps getting reactivated and
   suppresses alternatives. Stepping away lets that priming decay; on return you explore
   elsewhere. Incubation helps largely because you *forget the wrong path*, not because the
   mind solves it in the background.
2. **Consolidation (sleep).** Sleep abstracts structure and demonstrably improves insight.
3. **Associative recombination at low cognitive load.** Remote associations connect when
   goal-directed focus relaxes.

Two observations made the LLM version tractable and interesting:

- An LLM is **frozen between calls** — no continuous dynamics, no sleep, no background
  computation. So any "incubation" benefit in an LLM *cannot* be unconscious labor; it must
  be fixation-decay or input-priming. **This makes an LLM a clean testbed the brain can't be:
  we can ablate "background processing" by construction.**
- Several AI techniques are already incubation analogues that few people frame that way:
  **context reset** = fixation-decay; **self-consistency / tree-of-thought** = recombination
  by independent exploration; **continual learning / replay** = consolidation (training-time
  only).

But all of that presumes the LLM *fixates* to begin with. So the real first question became:
**do LLMs fixate at all?** The natural probe is the **Cognitive Reflection Test (CRT)** — the
canonical human fixation paradigm, where a fast, intuitive, *prepotent* answer is wrong and a
slower deliberate one is right (bat-and-ball, widgets, lily-pad).

---

## 2. The concept being tested

CRT is a **dual-process** structure: a fast/cheap path yields a prepotent answer that a
slow/deliberate path would override. Fixation = the fast path winning. The **trap answer** is
the prepotent wrong response; its rate is the direct fixation signature (not just accuracy).

What would count as fixation in an LLM:

- the model gives the **trap** (the prepotent wrong answer), and
- it does so more when **not** deliberating (fast / no chain-of-thought) than when it is.

We built every item with a deterministic **CORRECT** answer *and* a deterministic **TRAP**
answer, so each response is graded `CORRECT / TRAP / OTHER / UNPARSED`. Items are
re-skinned with fresh numbers (notebooks/pens, painters/murals, algae/ponds) so the trap is
not a memorized string.

---

## 3. The experiments and results

Four experiments, in the order run. Models are cheap/mid "flash"-class unless noted; the
fast modes ("no-CoT", "instinct") genuinely suppress serial reasoning on these.

### Experiment 1 — Does incubation (reset/distraction) help on CRT?
*(`bench/incubation/harness.py`; deepseek-v4-flash + gemini-2.5-flash, n=30 each.)*

Six compute-matched recovery strategies: `base` (one chain), `insist` (push in the same
context), `reset` (fresh context), `distract` (unrelated filler then fresh), `stepback`
(reframe first), `selfcons` (N fresh samples, majority).

**Result: 0 trap in 0/360 decisions.** Both models solved the CRT traps correctly on the
first try, so there was nothing to fixate on and nothing for reset/incubation to recover. The
pre-registered falsifier fired: **modern models do not fixate on canonical CRT.**

### Experiment 2 — Is it chain-of-thought that protects them?
*(`bench/incubation/harness_nocot.py`; same models, n=30.)*

Mechanistic test of "CoT puts the model in deliberate mode, which defeats CRT". If true,
stripping reasoning should bring the trap back. Three modes: `cot`, `nocot` (number only),
`instinct` ("don't calculate — first-instinct number").

**Result: 0 trap across all three modes, both models (0/180).** Even pure "instinct" mode
answered correctly. **This refuted the proposed mechanism.** The correct CRT resolution is
**saturated into the weights** — the right answer has become the *prepotent* one; the trap is
no longer a trap. (Side observation: on these saturated-easy items, CoT slightly *hurt*
gemini's parse reliability — overthinking a known answer added formatting noise.)

Implication: to see fixation you need **novel structure** the model hasn't memorized.

### Experiment 3 — Garden-path twists (novel structure, same surface)
*(`bench/incubation/harness_twist.py`, mixed families; deepseek + gemini-2.5, n=30 → 15
canonical + 15 twisted.)*

Same familiar CRT surface, but a twist that makes the memorized **template** answer wrong:

| family | canonical | twist | template trap (now wrong) |
| :--- | :--- | :--- | :--- |
| cost | "A costs $d more than B" | "A costs $d more than **TWICE** B" | (T−d)/2 |
| rate | "m workers make m units" | "m workers make **2m** units" | base time t |
| doubling | "...full day D; **half**?" | "...full day D; **one-quarter**?" | D−1 |

**Result:**
- canonical trap = 0 (control holds);
- deepseek twisted trap = 0 (robust to the twist, even fast);
- **gemini-2.5 twisted: cot 0 trap, but nocot 5 trap and instinct 5 trap — all on the *rate*
  family (5/5 rate-twists captured in fast mode).**

The phenomenon exists. gemini-2.5 applies the memorized template in fast mode and is corrected
by CoT — exactly the dual-process prediction. The earlier "CoT protects" mechanism, refuted on
saturated CRT, is **confirmed in refined form**: CoT protects against *template-capture on
novel structure*, not against saturated patterns (whose answer is already in the weights).

### Experiment 4 — Power round, 5 models (rate twist)
*(`bench/incubation/harness_twist.py --dataset rate`, n=24 → 16 twisted (2× and 3× units) + 8
canonical, per model.)*

TRAP = the exact template value (base time `t`); other wrong answers are `OTHER`, not fixation.

| model | twisted cot | twisted nocot | twisted instinct | fast trap |
| :--- | :--- | :--- | :--- | :--- |
| gpt-oss-120b | 0/16 | 0/16 | 0/16 | **0/32** |
| deepseek-v4-flash | 0/16 | 0/16 | 0/16 | **0/32** |
| gemini-3.1-flash-lite | 0/16 | 1/16 | 0/16 | **1/32** |
| qwen3-235b | 0/16 | 3/16 | 2/16 | **5/32** |
| gemini-2.5-flash | 0/16 | 6/16 | 8/16 | **14/32** |

Canonical: 0 trap for every model in every mode.

Three findings, now with cross-model power:

1. **The CoT → 0 dissociation is universal.** `cot` twisted-trap = **0/80** across all five
   models. Deliberation eliminates template-capture every time. The blind spot lives only on
   the fast path.
2. **Fast-mode susceptibility is strongly model-dependent — a spectrum.** Immune even fast
   (gpt-oss-120b, deepseek) → mild (gemini-3.1, qwen) → strong (gemini-2.5, up to 50% in
   instinct). It is not "LLMs fixate" or "don't"; it is *some* models, on novel structure, in
   fast mode.
3. **TRAP ≠ OTHER — two different failures.** deepseek and gemini-3.1 *do* make more errors
   in fast mode (7–9 `OTHER`), but **not the template** — their slips are other mistakes
   (half the trap, twice the correct). Only gemini-2.5 (and partly qwen) falls into the
   *specific memorized template*. So "fast mode is more error-prone" (general) is distinct
   from "fast mode falls into the template" (the specific fixation). deepseek genuinely tries
   to compute even without CoT and slips on the ratio; gemini-2.5 pattern-matches the template.

So CoT (or verification) is the antidote. But CoT is expensive — the practical question is
whether a *cheap* signal can tell you when to deploy it. Experiments 5–6 test that; 7 tests
what happens inside a recursive loop.

### Experiment 5 — Does self-consistency catch it? (no)
*(`bench/incubation/harness_selfcons.py`, rate twist, N=5 fast samples; gemini-2.5, qwen, n=24.)*

The popular cheap defense is sample-and-vote. It does **not** work here:

| model | single-sample TRAP | majority-vote TRAP |
| :--- | :--- | :--- |
| gemini-2.5 | 18% | **19%** |
| qwen3-235b | 8% | **12%** |

Voting is no better (slightly worse). The raw shows why: a template-captured model returns the
**same** trap on every sample (`[8,8,8,8,8]`), so majority locks it in. Self-consistency
averages out *random* error; template-capture is *systematic*. → the right cheap defense is
**re-derivation/verification, not consensus.**

### Experiment 6 — Is there a cheap in-run detector? (partly, and model-dependent)
*(`bench/incubation/harness_detector.py`, rate twist; gemini-2.5, qwen, n=24.)*

Two cheap candidate triggers for "escalate to deliberation":

- **Self-reported confidence — useless.** Mean confidence on TRAP answers ≈ on CORRECT answers
  (~95–100) in both models. The model is just as sure when template-captured as when right; the
  prepotent answer *feels* right.
- **A novelty flag** ("without solving, does this DEVIATE from the standard version?") —
  **works for one model, fails for the other:**

  | model | DEVIATES \| twisted | DEVIATES \| canonical (false alarm) | usable trigger? |
  | :--- | :--- | :--- | :--- |
  | qwen3-235b | 100% | 12% | yes — clean separation |
  | gemini-2.5 | 75% | 88% | no — cries "twist" on everything |

The irony: the model that fixates *most* (gemini-2.5) has the *worst* self-detector. A cheap
detector is **possible in principle** (qwen proves it) but **not dependable across models**, and
the model that needs it most can't produce it.

### Experiment 7 — The recursive loop: does one fixation poison the chain, and does one gate save it?
*(`bench/incubation/harness_chain.py`, 3-stage chain, n=24; gemini-2.5 (fixates) + deepseek (robust).)*

A 3-stage chain where each stage **re-injects the previous result as an established fact**
(stage 1 = the rate twist; stage 2 multiplies it; stage 3 divides into shifts) — the
"artifacts become state surfaces" structure, made deterministic. Two pipelines: `naive` (every
stage fast) vs `gate@1` (deliberate **only** at stage 1, the fixation point).

| model | pipeline | chain CORRECT | chain TRAPPED | stage-1 wrong | carried faithfully |
| :--- | :--- | :--- | :--- | :--- | :--- |
| gemini-2.5 | naive | **15/24 (62%)** | 4 | 9/24 | **9/9** |
| gemini-2.5 | **gate@1** | **24/24 (100%)** | 0 | 0/24 | — |
| deepseek | naive | 22/24 | 0 | 2 (slips) | 2/2 |
| deepseek | gate@1 | 22/24 | 0 | 2 (CoT parse-fail) | — |

Three results:
1. **The "ditch" is real.** On the fixating model, a stage-1 error reaches the FINAL answer in
   9/24 = 38% of chains — the single cheap fixation poisons the whole recursion.
2. **It's propagation, not amplification (honest nuance).** All 9 poisoned chains were *carried
   faithfully*: stages 2–3 computed correctly on the wrong premise. The model doesn't make
   *more* errors downstream; it rides a wrong premise to a confidently-wrong conclusion. True
   amplification would need generative elaboration; deterministic arithmetic just carries.
3. **One gate at the fixation point rescues the whole chain.** `gate@1` (deliberate only at
   stage 1): 62% → **100%**. You don't deliberate everywhere — you place the gate where the
   cheap path is unreliable. On the *robust* model the gate is wasted (naive ≈ gate@1) and CoT
   even adds 2 parse-fails ("overthinking" noise). The vulnerability is targeted; so is the fix.

---

## 4. Conclusion

**The arc.** Classic CRT does **not** transfer to LLMs — not because chain-of-thought enforces
deliberation (we tested and refuted that), but because the correct resolution is **saturated
into the weights** as the prepotent response. Fixation, where it exists, requires **novel
structure**: a garden-path twist with a familiar surface. There, it appears as textbook
**dual-process** behavior — the fast path applies the memorized template (the trap), and
deliberation (CoT) overrides it.

**The measured claims:**
- **Universal:** CoT eliminates template-capture in every model tested (0/80).
- **Model-specific:** susceptibility to the fast-path template trap ranges from 0 (gpt-oss,
  deepseek) to ~50% in instinct mode (gemini-2.5). The *antidote* (deliberation) is
  model-independent in its effectiveness; the *vulnerability* is not.
- **Mechanistically split:** fast mode degrades many models, but only some fall into the
  specific template attractor; the rest just make ordinary errors.

**The cheap defenses don't substitute for it.** Self-consistency fails (the trap is a
*stable*, systematic error — voting locks it in). Confidence fails (the model is confidently
wrong). A cheap "is this novel?" flag works for some models and not others, and the model that
fixates most can't self-detect. So there is no reliable cheap shortcut for "when to escalate";
the dependable floor is to **deliberate or verify** — and verification (compute the answer in
code) is exactly the gate-REPL discipline of this project.

**Why it matters beyond CRT.** This is the dual-process vulnerability a **cognitive
architecture** re-introduces. A single chain-of-thought LLM is relatively safe *because it is
monolithically deliberate*. The moment you build an architecture around it — a router, a
cache, a fast draft, a cheap framing step in a recursive harness — you add a **fast shortcut
path**, and that path inherits the blind spot: it misfires on novel structure exactly like a
model in "instinct" mode. **And in a recursive loop the cost compounds: Experiment 7 shows a
single stage-1 fixation poisons 38% of chains, carried faithfully to a confidently-wrong final
answer — while one gate placed at the fixation point rescued 100%.** That is the "engineering
ritual that stops a task being negotiated into a ditch", measured: not blanket deliberation
(wasted on robust models, and it even adds noise), but a **gate placed where the cheap path is
unreliable**. The right architectural rule is therefore *"verify on novelty,"* not *"deliberate
everywhere"* and not *"pick a robust model"* — the same grounding/verification primitive
(belief-gate / gate-REPL) and the same restraint primitive (engage the slow path when the fast
signal can't be trusted) seen throughout this project.

**Honest scope.** n is modest (16 twisted items per mode per model); the small trap counts in
the middle of the spectrum (gemini-3.1 = 1, qwen = 5) should not be over-ranked. What is solid:
(a) `cot = 0/80` universal; (b) gemini-2.5 clearly fixates in fast mode (14/32, up to 8/16);
(c) gpt-oss-120b and deepseek are clearly immune to the template. The fine ordering between
the mild models is suggestive, not established. And this measures one trap family (rate) most
heavily; cost/doubling twists captured gemini-2.5 less, so structure matters too.

(Experiment 7 scope: n=24, one fixating + one robust model; the 62%→100% contrast is
within-model and clean, and 9/9 poisoned chains carried faithfully — but don't read it as
"all chains, all models". It demonstrates the mechanism, not a universal rate.)

**One line.** *Classic CRT is memorized away; real LLM fixation lives in novel garden-path
structure, behaves as pure System-1 template-capture (present in fast mode, erased by CoT in
every model), is model-specific in magnitude, propagates faithfully through a recursive chain
(38% of chains poisoned by one stage-1 fixation), and is stopped by a single gate placed at
the fixation point (62%→100%) — the same dual-process blind spot cheap shortcut paths
re-introduce into cognitive architectures, defended by the same "verify-on-novelty" primitive
(belief-gate / gate-REPL) that the rest of this project is built on. Cheap proxies — voting,
confidence — do not substitute for it.*

---

## 5. Reproduce

```bash
# 1. does reset/incubation help on canonical CRT?  -> 0 trap (no fixation)
python -m bench.incubation.harness --n 30 --model <M>
# 2. is it CoT that protects?  -> 0 trap even in instinct mode (saturation, not CoT)
python -m bench.incubation.harness_nocot --n 30 --model <M>
# 3. garden-path twist (novel structure)  -> fixation appears, CoT catches it
python -m bench.incubation.harness_twist --n 30 --model <M>
# 4. power round, rate twist, many models  -> cot 0/80; fast trap model-dependent
python -m bench.incubation.harness_twist --dataset rate --n 24 --model <M>
# 5. does self-consistency catch it?  -> no (majority ≈ single; stable systematic error)
python -m bench.incubation.harness_selfcons --n 24 --samples 5 --model <M>
# 6. cheap in-run detector?  -> confidence useless; novelty-flag model-dependent
python -m bench.incubation.harness_detector --n 24 --model <M>
# 7. recursive loop: does one fixation poison the chain; does one gate save it?
python -m bench.incubation.harness_chain --n 24 --model <M>
```

Generators and graders: `bench/incubation/dataset.py`, `dataset_twist.py`, `dataset_chain.py`.
Each item carries a deterministic CORRECT and TRAP; graders classify CORRECT / TRAP / OTHER (and
CHAIN_CORRECT / CHAIN_TRAPPED for the loop). Raw per-item results land in `results/*.jsonl`.
