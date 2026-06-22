# The Mythos: anti-runaway primitives for recursive frozen-core systems

*A synthesis. Three primitives that keep a recursive system built around a frozen
inference core from trusting its own output — grounding, restraint, anchoring — each now
measured in a clean substrate. The through-line, and what is still open.*

---

## 1. The question

A modern LLM is a **frozen** inference core: no memory, no learning between calls. The
intelligence of a *system* built around it does not live in the weights — it lives in the
**external structure (the harness)** that rebuilds the context recursively each step, where
the output of one stage configures the next. (This is the "Mythic Layer" framing of
recursive harnesses; the term *Mythos* is ours for that layer.)

The danger is also recursive. As one reviewer put it: **"recursive state can start being
mistaken for proof — if artifacts can call the model again, they're no longer outputs, they
become state surfaces,"** and the task gets *"negotiated into a ditch."* So the "mythic" part
is not magic — it is the **engineering rituals that stop the recursion from believing itself.**

**Hypothesis.** Those rituals are not one thing. They decompose into a small set of
**anti-runaway primitives**, and the primitives are substrate-independent — the same shape
recurs in LLM harnesses, in adaptive control, and (arguably) in predictive brains. We name
three and, in this project, measured each.

**The common form (the thesis in one line):**

> In a recursive system, a **local / cheap** signal tends to override the **standing /
> correct** one — unless an **external anchor** is engaged. The anchor takes three forms:
> *verify* the state, *deliberate* before committing, *re-inject* the objective. Each is a
> way of refusing to let the loop trust its own cheap output.

---

## 2. The three legs (each measured)

### Grounding — *verify the state against its source before trusting it*
**Guards against:** an unverified / incomplete artifact being treated as proof.
**Mechanism:** completeness/coherence by execution (set difference, coverage invariant,
source fingerprint), not by judgment. This is **belief-gate / gate-REPL**.

**Measured:**
- An LLM judging "is this context complete?" false-passes on subtle interior gaps — **7/15
  (gemini), 2/15 (deepseek)**. Moving the check into executed code drops that to **0/15, both
  models.** The library is leak-proof (29/29 tests; 9,580 exhaustive decisions, 0 errors).
- Cross-model, the deterministic gate is the only method that is 0-dangerous + 0-false-alarm
  + 0-cost on every model; a strong model (gemini-2.5) confabulated a wrong total **35%** of
  the time when a slice was silently missing.
- **End-to-end double dissociation:** routed through LLM→gate→REPL, a computable question is
  answered exactly or abstained — **80/80 correct, 80/80 abstain** — while the same models
  answering directly score 3–6/80 on the arithmetic (gemini: **0/40**).

*(`bench/realqa/`, `beliefgate/`; full study in `docs/GATE_REPL.md`, `docs/FINDINGS.md`.)*

### Restraint — *don't trust the cheap/fast signal on novelty; deliberate or verify*
**Guards against:** the fast path applying a memorized template / prepotent answer where it
misfires.
**Mechanism:** engage the slow path (deliberation) or a verifier when the input is novel.

**Measured** *(`bench/incubation/`; full study in `docs/INCUBATION_FIXATION.md`)*:
- Classic CRT does **not** fool modern models (0/360) — the answer is saturated into the
  weights. Fixation requires **novel "garden-path" structure**.
- There it is textbook System-1 template-capture: present in fast mode, **erased by CoT in
  every model (0/80)**; magnitude is **model-specific** (gpt-oss/deepseek immune, gemini-2.5
  up to ~50% in instinct mode).
- **The cheap shortcuts don't substitute.** Self-consistency fails (the trap is a *stable*
  systematic error — voting locks it in); confidence is useless (the model is confidently
  wrong); a cheap novelty-flag works for one model and not another.
- **In a recursive loop:** a single stage-1 fixation poisons **38%** of chains (carried
  faithfully to a confidently-wrong final answer); **one gate placed at the fixation point
  rescued 100%** (62%→100%). Deliberation is wasted on a robust model and even adds noise —
  so the rule is *place the gate where the cheap path is unreliable*, not everywhere.

### Anchoring — *hold the objective/identity invariant across the reconstruction*
**Guards against:** the standing objective/identity drifting as the recursion proceeds and
local pressures accumulate.
**Mechanism:** re-inject the canonical objective/identity each step, instead of letting it
fade.

**Measured** *(`bench/anchoring/`)*: a multi-turn dialogue establishes a checkable identity
(a required tag + a persona signature), then applies drift pressure (turns demanding terse
output that competes with the rule). `naive` states the rule once; `anchored` re-injects it
each turn.
- A **salient** constraint (the formatting tag) is held **100%** regardless — strong rules
  don't drift, so anchoring is unnecessary for them.
- A **soft** constraint (the persona identity) **drifts in `naive` specifically on pressure
  turns — 73%** retained — and **`anchored` holds it at 100%**, *identically in both models.*
  The drift is pressure-triggered (a local "answer in one word" instruction overrides the
  faded identity), not gradual decay.

---

## 3. The through-line

The three legs are the same move on three axes:

| Leg | the cheap signal that wins | the standing thing it overrides | the external anchor |
| :--- | :--- | :--- | :--- |
| **Grounding** | "it looks complete" (judgment) | what the task actually requires | **verify** (set diff / REPL) |
| **Restraint** | the memorized template (fast path) | the correct answer to a novel item | **deliberate / verify** |
| **Anchoring** | a local instruction ("one word only") | the standing objective / identity | **re-inject** the anchor |

And each guards a different failure of the *same* recursion: ungrounded state mistaken for
proof (grounding), a cheap step poisoning the chain (restraint — measured propagating 38%,
rescued by a placed gate), the objective drifting under accumulated pressure (anchoring).

**The architectural rule that falls out:** a single chain-of-thought LLM is relatively safe
*because it is monolithically deliberate and self-contained*. The moment you build an
architecture around it — a router, a cache, a fast draft, a recursive harness — you add cheap
shortcut paths, and each re-introduces one of these blind spots. The defense is not "pick a
robust model" and not "deliberate/verify everywhere" (wasteful, and it adds noise). It is
**place the anchor where the cheap path is unreliable**: verify the enumerable state, engage
the slow path on novelty, re-inject the objective each step.

---

## 4. What is NOT settled (the honest frontier)

- **The detector is characterized, and it hits one wall.** We proved the *antidotes*
  (verify / deliberate / re-inject), not a *cheap in-run trigger* for when to fire them — but we
  now know its shape. A detector is a **decorrelated residual** between two estimators; catch
  scales with decorrelation (self-consistency 22% → paraphrase 44% → execution 100%) and the
  axis *terminates at execution*, so the detector and grounding are one continuum. Its limit is
  **false-alarm**, and the one failure no cheap residual cracks — at re-sample, cross-task, or
  intra-network scale — is the **systematic, confident error correlated across every cheap
  view**. The white-box channel that might attack it is dead for lack of substrate (no cheap
  model both fixates and exposes activations). So the floor remains the (more expensive)
  antidote, and the open problem is now a *named wall*, not a mystery. Full study:
  [DETECTOR.md](DETECTOR.md); the grounding-at-scale deflation: [FINQA.md](FINQA.md).
- **Implementation ≠ primitive.** The anchoring *primitive* is real (measured here), but a
  *sophisticated mechanism* for it can still fail: the Aura/LCO JEPA-injection mechanism
  failed its own cheap causal-work gate (wrong-prompt atoms produced byte-identical output;
  `C1 ≈ baseline` on compliance). That validation is separate and ongoing in its own repo;
  it does not bear on whether anchoring-as-a-primitive works (it does).
- **Scope is modest.** n is small throughout (15–120 per cell; anchoring n=8 dialogues × 2
  models). The contrasts that are *clean and repeated across models* are the load-bearing
  ones (gate 0/15; CoT 0/80; anchoring 73%→100% identical in two models; loop 62%→100%); the
  fine rankings in the middle of each spectrum are suggestive, not established.
- **The anchored arm is "re-prompting."** Anchoring works = re-stating the objective each
  step keeps it. That is precisely the architectural choice (a canonical-context / UserHarness
  re-injection) — but it is not a subtle mechanism, and the measured contribution is
  *quantifying that the soft identity does drift under pressure and that re-injection fixes it*,
  not inventing a new technique.
- **One substrate measured per leg.** The cross-substrate claim (these are the *same*
  primitives in control loops and brains) remains an analogy — suggestive, not formalized.

---

## 5. Relation to the rest of the project

The Mythos is the *theory*; **belief-gate / gate-REPL is the shippable part of it** — the
grounding leg, packaged as a zero-dependency library, an MCP server, and a Claude Code skill
(`beliefgate/`, `docs/FINDINGS.md`). Restraint and anchoring are, for now, *measured findings*
rather than products: the practical takeaway is the architectural rule above (*verify on
novelty; re-inject on drift; place the gate where the cheap path is unreliable*), and the
honest caution that no cheap detector yet tells you where that is.

**One line.** *The Mythos — the layer that keeps a recursive frozen-core system coherent — is
not magic; it is three anti-runaway primitives (verify, deliberate, re-inject), each a way of
refusing to let the loop trust its own cheap output, each now measured: grounding (0/15 vs
7/15, and 80/80 end-to-end), restraint (CoT erases template-capture 0/80; one placed gate
rescues a poisoned chain 62%→100%), anchoring (soft-identity drift 73%→100% under
re-injection). The open problem is not the cure but the diagnosis: a cheap way to know,
in-run, where the cheap path is about to fail.*
