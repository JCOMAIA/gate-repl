# Keeping a recursive frozen-core system from trusting itself

*A theory with one shippable leg. A modern LLM is a **frozen** inference core — no memory,
no learning between calls. The intelligence of a **system** built around it lives not in the
weights but in the **harness** that rebuilds the context recursively each step. That recursion
has a characteristic failure: a **cheap, local signal** starts overriding the **standing,
correct** one, and the task gets negotiated into a ditch. This project names the failure,
decomposes the defense into three measurable primitives, and ships the one that is a product.*

---

## TL;DR

- **The thesis.** In a recursive system, a *cheap/local* signal tends to override the
  *standing/correct* one — unless an **external anchor** is engaged. The anchor takes three
  forms: **verify** the state, **deliberate** before committing, **re-inject** the objective.
- **Each measured.** Grounding (verify): an LLM completeness-judge false-passes **7/15**; the
  executed check, **0/15**; end-to-end **80/80 correct + 80/80 abstain**. Restraint
  (deliberate): chain-of-thought erases template-capture **0/80**; one placed gate rescues a
  poisoned recursive chain **62%→100%**. Anchoring (re-inject): a soft identity drifts under
  pressure **73%**, re-injection holds it **100%** — identical in two models.
- **What ships.** **belief-gate / gate-REPL** — the grounding leg, as a zero-dependency
  library, an MCP server, and a Claude Code skill. The other two legs are measured findings,
  not products.
- **The honest frontier.** We proved the *antidotes*, not a *cheap in-run detector* for when
  to fire them. That diagnosis problem is still open — and we tested the best candidate
  (below) and it is not deployable.

---

## 1. The problem

An LLM call is stateless and deliberate. A *single* chain-of-thought answer is relatively
safe precisely because it is monolithic and self-contained. The moment you build an
architecture around the core — a router, a cache, a fast draft, a multi-stage harness where
**the output of one stage configures the next** — you introduce cheap shortcut paths, and the
recursion acquires a new class of failure:

> **Recursive state gets mistaken for proof.** "If artifacts can call the model again, they're
> no longer outputs — they become state surfaces," and the task gets *"negotiated into a
> ditch."* *(reviewer framing that seeded this work.)*

The "mythic" layer that keeps such a system coherent is not magic. It is a small set of
**engineering rituals that stop the recursion from believing its own cheap output.** This
project's claim is that those rituals **decompose into three primitives**, and that each can be
measured in a clean substrate.

---

## 2. The three primitives (each measured)

### Grounding — *verify the state against its source before trusting it*
**Failure guarded:** an unverified / incomplete artifact treated as proof.
**Mechanism:** completeness by **execution** (set difference, coverage invariant, source
fingerprint), never by judgment. This is **belief-gate / gate-REPL**.

| finding | result |
| :--- | :--- |
| LLM judging "is this context complete?" | false-passes **7/15** (gemini), **2/15** (deepseek) |
| same check moved into executed code | **0/15**, both models |
| library guarantee | leak-proof: 29/29 tests, **9,580 exhaustive decisions, 0 errors** |
| strong model over a silently-missing slice | confabulates a wrong total **35%** of the time |
| end-to-end (LLM→gate→REPL) on computable QA | **80/80 correct, 80/80 abstain**; same models direct: **3–6/80** arithmetic (gemini **0/40**) |

**At scale, honestly (FinQA, 5 models):** the deterministic core holds (548 items, gate
leak-proof 548/548, executor faithful 98.7%), but the dramatic toy result **deflated** — the
gate does **not** beat a calibrated `direct` baseline on confabulation (gate 25% vs direct 17%
macro). What survives: execution buys accuracy (+5 pts), and the gate makes execution *safe*
(it recovers the calibration plain PAL loses). The gate's value is making the accuracy path
honest, not replacing native calibration. See §5 and [FINQA.md](FINQA.md).

*Deep dive: [GATE_REPL.md](GATE_REPL.md), [FINDINGS.md](FINDINGS.md), [FINQA.md](FINQA.md); code `bench/realqa/`, `bench/finqa/`, `beliefgate/`.*

### Restraint — *don't trust the fast path on novelty; deliberate or verify*
**Failure guarded:** the fast path applying a memorized template where it misfires.
**Mechanism:** engage the slow path (deliberation) or a verifier when the input is novel.

| finding | result |
| :--- | :--- |
| classic CRT (memorized) | does **not** fool modern models — **0/360** (saturated into weights) |
| novel "garden-path" structure | template-capture appears in fast mode; **model-specific** (gpt-oss/deepseek immune, gemini-2.5 up to ~50%) |
| chain-of-thought | **erases it in every model — 0/80** (the universal antidote) |
| cheap shortcuts | self-consistency fails (stable trap → vote locks it in); confidence is useless (confidently wrong) |
| recursive loop | one stage-1 fixation poisons **38%** of chains (propagated faithfully); **one placed gate rescues 100% (62%→100%)** |

*Deep dive: [INCUBATION_FIXATION.md](INCUBATION_FIXATION.md); code `bench/incubation/`.*

### Anchoring — *hold the objective/identity invariant across the reconstruction*
**Failure guarded:** the standing objective drifting as local pressures accumulate.
**Mechanism:** re-inject the canonical objective each step instead of letting it fade.

| finding | result |
| :--- | :--- |
| **salient** constraint (a required format tag) | held **100%** regardless — strong rules don't drift; anchoring unneeded |
| **soft** constraint (a persona identity), naive | drifts specifically on pressure turns — **73%** retained |
| same, with per-turn re-injection | **100%** — *identical in both models*; drift is pressure-triggered, not gradual decay |

*Code `bench/anchoring/`.*

---

## 3. The through-line

The three legs are the same move on three axes:

| Leg | the cheap signal that wins | the standing thing it overrides | the external anchor |
| :--- | :--- | :--- | :--- |
| **Grounding** | "it looks complete" (judgment) | what the task actually requires | **verify** (set diff / REPL) |
| **Restraint** | the memorized template (fast path) | the correct answer to a novel item | **deliberate / verify** |
| **Anchoring** | a local instruction ("one word only") | the standing objective / identity | **re-inject** the anchor |

**The architectural rule that falls out:** the defense is *not* "pick a robust model" and
*not* "deliberate/verify everywhere" (wasteful, and it adds noise). It is **place the anchor
where the cheap path is unreliable** — verify the enumerable state, engage the slow path on
novelty, re-inject the objective each step.

---

## 4. What ships, and what doesn't

| | status | where |
| :--- | :--- | :--- |
| **belief-gate / gate-REPL** (grounding) | **product** — zero-dep library, MCP server, Claude Code skill, runnable quickstart | `beliefgate/`, `plugins/belief-gate/` |
| Restraint | measured finding → the architectural rule | `docs/INCUBATION_FIXATION.md` |
| Anchoring | measured finding → re-injection rule | `bench/anchoring/` |

The theory is the **Mythos**; belief-gate is the **shippable part of it**. Restraint and
anchoring are, for now, findings that yield an architectural rule, not packaged tools.

---

## 5. The honest frontier (what is *not* settled)

- **The detector is characterized, and it hits a wall.** We proved the *antidotes*
  (verify / deliberate / re-inject), not a *cheap in-run trigger* for when to fire them — and we
  now know *why*. A detector is a **decorrelated residual** between two estimators; catch scales
  with decorrelation (measured: self-consistency 22% → paraphrase 44% → execution 100%), and the
  axis *terminates at execution* (so the detector and belief-gate are one continuum). But the
  residual is gated by **false-alarm**, and the one thing no cheap residual cracks — at any scale
  (re-sample, cross-task, intra-network) — is the **systematic, confident error that is
  correlated across every cheap view**. The white-box channel that might have attacked it is
  dead for lack of substrate (no cheap model both fixates and exposes activations). That single
  wall, not any sensor's win, is the result. Full thread: [DETECTOR.md](DETECTOR.md).
- **Grounding deflates at scale.** The toy gate result did not survive FinQA: against a
  calibrated `direct` baseline the gate does not reduce confabulation (it only cleans up PAL).
  The honest claim is narrower — *execution buys accuracy; the gate makes execution safe* — not
  *the gate makes a model more honest than asking it directly*. See [FINQA.md](FINQA.md).
- **Implementation ≠ primitive.** The anchoring *primitive* is real; a *sophisticated
  mechanism* for it can still fail. A separate JEPA-injection implementation (the Aura/LCO
  line) failed its own cheap causal-work gate (wrong-prompt atoms → byte-identical output);
  that validation is ongoing in its own repo and does not bear on whether anchoring-as-a-
  primitive works (it does).
- **Scope is modest.** n is small throughout (15–120 per cell; anchoring n=8 dialogues × 2
  models). The load-bearing results are the **clean contrasts repeated across models** (gate
  0/15; CoT 0/80; anchoring 73%→100% identical in two models; loop 62%→100%); fine rankings in
  the middle of each spectrum are suggestive, not established.
- **One substrate per leg.** The cross-substrate claim (these are the *same* primitives in
  control loops and predictive brains) remains an analogy — suggestive, not formalized.

---

## 6. Use it

```bash
pip install -e beliefgate            # zero-dependency core
belief-gate-demo                     # runnable 3-mode quickstart
pip install -e "beliefgate[mcp]"     # + MCP server (belief-gate-mcp)
```

The Claude Code skill lives in `plugins/belief-gate/`. Integration notes:
[beliefgate/INTEGRATION.md](../beliefgate/INTEGRATION.md).

---

## 7. Map of the work

| document | what it covers |
| :--- | :--- |
| **this file** | the consolidated narrative (belief-gate + Mythos) |
| [MYTHOS.md](MYTHOS.md) | the three-primitive synthesis in full |
| [GATE_REPL.md](GATE_REPL.md) | grounding: the full gate / gate-REPL study |
| [FINDINGS.md](FINDINGS.md) | grounding: cross-model + end-to-end results |
| [INCUBATION_FIXATION.md](INCUBATION_FIXATION.md) | restraint: the fixation study (7 experiments + the loop) |
| [FINQA.md](FINQA.md) | grounding at scale on a public benchmark — and the honest deflation |
| [DETECTOR.md](DETECTOR.md) | the detector frontier: the decorrelated residual and its one wall |
| [SCENARIOS.md](SCENARIOS.md) | where the gate helps vs where it doesn't (measured boundaries) |
| [UNIFICATION.md](UNIFICATION.md) | the gate as a unification primitive (source) |

---

*One line. The layer that keeps a recursive frozen-core system coherent is not magic; it is
three anti-runaway primitives — verify, deliberate, re-inject — each a way of refusing to let
the loop trust its own cheap output, each measured. What ships is the first one (and at scale it
buys safety, not honesty-over-baseline). The diagnosis — a cheap in-run trigger for when the
cheap path fails — is now characterized, not solved: it is a decorrelated residual, and the one
thing it cannot crack is the systematic-confident error correlated across every cheap view —
the same wall at every scale, with no cheap white-box substrate to attack it.*
