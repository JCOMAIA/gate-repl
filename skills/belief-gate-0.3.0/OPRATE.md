# The Operationalization Rate: mapping the decidable-vs-semantic frontier

*Every thread of this program hit the same boundary — the gate works on the decidable slice,
the detector dies on the semantic one, BINEVAL helps most on concrete criteria, O'Neill's
Order/Entropy split assumes it. Everyone points at the frontier; nobody had mapped it. This
study builds the instrument, takes a first map, and tests whether the map-making itself can be
delegated to a cheap LLM. Code: `bench/oprate/`.*

---

## 1. The question

In a real domain, **what fraction of the decisions can be converted into an executable or
observable check — and at what cost?** If the fraction is high, the "semantic problem" is
mostly drainage work (move decisions to code/execution); if low, verification is structurally
out of reach. The answer decides where engineering effort should go.

## 2. The instrument (taxonomy + audit rule)

Each decision, **as phrased**, gets exactly one class:

| class | meaning | escapes S_core only by… |
| :--- | :--- | :--- |
| **D** | decidable now — deterministic check against an available structured source | naming the check + source |
| **OE** | settled by *executing* something and observing (build/test/benchmark/staging) | naming the executable prediction |
| **OW** | settled by a real-world consequence, later or at cost (metric after a cycle, a ruling) | naming the outcome + delay |
| **S_spec** | semantic *by under-specification* — writing the contract/policy converts it to D/OE | naming the converting spec |
| **S_core** | genuine residue — interpretation, preference, values | (default) |

**The audit rule is the anti-slop mechanism:** the default is S_core, and a label escapes only
by *naming* its decider. You cannot claim "decidable" without saying what decides it.

The **S_spec / S_core split** is the taxonomy's main move: the Unity-manifest experience showed
"is the level done?" is semantic until you write the manifest — then it is a set difference.

## 3. Stage 1 — pilot map (n=53)

Corpus: 12 real FinQA analyst questions (mechanically sampled) + 41 curated realistic decisions
(office 15, code review 14, legal 12).

| domain | D | OE | OW | S_spec | S_core | operationalizable |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: |
| finqa | 12 | – | – | – | – | **100%** |
| office | 10 | – | 1 | 3 | 1 | **73%** |
| code | 4 | 6 | – | – | 4 | **71%** |
| legal | 6 | – | 1 | 2 | 3 | **58%** |
| **total** | 32 | 6 | 2 | 5 | 8 | **75.5%** |

Readings: **72% of decisions are operationalizable *now*** (D+OE); the genuine semantic residue
is **15%**; and **38% of the apparent "semantic valley" is spec debt, not semantics** — the
cheapest lever against the semantic problem is *writing the contract*, not better AI.
Conversion cost skews low (17 trivial, 20 moderate, 1 heavy).

## 4. Stage 2 — wild validation (25 real review comments)

To remove corpus-authorship circularity: 25 real cpython/vscode review comments, mechanically
sampled and filtered, audit-labeled.

- **5/25 are not decisions at all** (coordination talk) — a wild-only finding.
- Operationalization rate on the wild decisions: **65%** (pilot code domain: 71% — consistent).
- **The pilot's linguistic signature did *not* transfer** (evaluative-term regex: 0/7 wild
  S_core hits — the lexicon was domain/language-specific). An expanded hedging lexicon
  (prefer / rather / make sense / propose / think) recovers recall **86%** but false-alarms
  **38%** on operationalizable items. The signal *bleeds* — the same catch/FA structure as
  every cheap detector in `DETECTOR.md` (paraphrase 44/38, expr 100/38). Not a free
  stall-warning; a calibratable noisy one.
- Epistemic note: the labeler knew the hypothesis and the signature still failed —
  failure against a confirmation bias is the more credible for it.

## 5. Stage 3 — can a cheap LLM run the router? (v1)

deepseek-chat classifies all 61 audited decisions (n=61, 0 dead). **Exact match 66%, Cohen's
kappa 0.486** (top of the judge range Norman et al. measured — this *is* LLM-as-judge
territory, and it behaves like it).

**Extremes solid, borders collapse** (pre-registered, confirmed): D **85%**, S_core **80%**,
OW 2/2 — but OE **23%** (mostly →D, harmless-ish: both operationalizable) and S_spec **20%**.

**Dangerous errors** (semantic classified as gateable → the router would commission a fake
gate): **6/20 (30%), all silent**, decomposing into exactly two failure modes:
1. **Silent spec-assumption** (3) — the router resolves S_spec by *inventing* the missing
   threshold/DMS/registry ("check the payroll delta against a **pre-defined** threshold" —
   defined by whom?). This is the declaration study's *silent ambiguity resolution*, one level
   up.
2. **Proxy-check substitution** (2–3) — a decidable check that answers a *different, easier*
   question ("compare timestamps" ≠ "is the doc semantically outdated?"). Misselection at the
   meta-level.

Bonus: disagreements audit the *reference* too — the router called "who approves a R$12k
purchase" S_spec where the reference said D (assuming the approval matrix exists). Both
defensible: see §6(b).

## 6. Stage 4 — the fix experiment (v2: forced ASSUMES + anti-proxy rule)

Same 61 items; prompt adds two rules (name a check that decides *this* question, not a proxy —
with the literal timestamp counter-example; declare assumed infrastructure under `ASSUMES`,
and downgrade to S_spec if the check is impossible without an unwritten spec).

| metric | v1 | v2 |
| :--- | :-: | :-: |
| kappa | 0.486 | 0.463 |
| dangerous total | 6/20 | 4/20 |
| **dangerous-and-SILENT** | **6/6** | **1/4 (−83%)** |
| proxy-check errors | 3 | **0** (fully fixed) |
| silent-spec-assumption class | 3 | 4 — *persists, but declared* |
| over-caution D→S_spec (safe) | 2 | 5 |

Scorecard vs pre-registration: the visibility target hit (P3 ✓); the proxy rule worked *better*
than predicted (P2 exceeded — the in-prompt counter-example did it); the S_spec→D class did
**not** shrink (P1 ✗) — the router *declares the assumption and keeps D* instead of
downgrading; over-caution regression as predicted (P4 ✓).

**Two findings beyond the scorecard:**

**(a) The fix delivers visibility, not elimination.** Of the 4 remaining dangerous errors, 3
arrive with the assumption declared ("ASSUMES: a report tracking system exists") — a human
audits in seconds ("do we have one?"). The error didn't vanish; it became cheap to catch. And
`ASSUMES` on *correct* items is a free byproduct: the gate's deploy-prerequisites list.

**(b) The D/S_spec boundary is observer-relative.** The router called "is the News entry
present?" S_spec; the reference said D — because the News rule *is* codified in cpython's CI,
which the reference knew and the router (text-only) didn't. Same for the court-fee formula
(exists in the CPC). Classification depends on **what infrastructure the classifier knows
exists**. Neither label is wrong; the taxonomy needs a declare-assumed-infrastructure rule —
the external-observer requirement applying to the map itself.

**The residual (the wall, in its finest form):** the one remaining *silent* dangerous error
smuggled the semantics **inside the check's wording**: *"search the contract text for 'cláusula
de rescisão' or synonyms/phrases with equivalent legal meaning"* — reads like a grep; "equivalent
legal meaning" is not a grep. No prompt rule closes this; a human reading the named check does.

## 7. Findings (numbered, honest)

1. **~72–75% of real decisions are operationalizable now**; the genuine semantic residue is
   ~15% (pilot; wild code slice consistent at 65%).
2. **~38% of the "semantic valley" is spec debt** — convertible by writing the contract.
3. **No free linguistic stall-warning**: the signature exists but bleeds (86% recall / 38% FA
   on wild data) and its lexicon is domain-specific.
4. **A cheap LLM router is judge-grade** (kappa ~0.46–0.49): reliable at the extremes
   (D 85%, S_core 80%), unreliable at the borders (OE, S_spec ~20%).
5. Its dangerous failures are **two named modes** — silent spec-assumption and proxy-check
   substitution — and forcing a `LABEL / CHECK / ASSUMES` declaration cuts *silent* dangerous
   errors by ~83% and zeroes the proxy class, at a small over-caution cost.
6. **The routing decision cannot be made deterministic** (it is itself semantic; the boundary
   is even observer-relative) — but it can be **shrunk to a seconds-long human audit** of a
   named check and declared assumptions.

## 8. Limitations (read before citing)

- **One labeler, and it is an LLM** — reference labels are audited (every one names its
  decider) but not ground truth. The honest full study needs 2–3 *decorrelated* human labelers
  + inter-rater kappa, on wild-sampled items across domains. (The instrument's own fix is the
  program's decorrelation principle.)
- Corpus mostly curated (only finqa + wild-code slices are mechanically sampled); n small
  throughout; one router model tested (deepseek-chat), one run each.
- "As phrased" sensitivity is a feature (it *is* the S_spec finding) but means rates are not
  comparable across differently-written corpora.

## 9. Relation to the program

This study is the cartography stage of the semantic-problem ladder (shrink → decompose →
decorrelate → **operationalize** → accumulate → declare): it measures how much of the valley
each rung can drain. It also closes the loop on the **gate-fabricator**: the fabricator's
front door (deciding what is gateable) is semantic and stays semantic — but router-v2 +
`CHECK`/`ASSUMES` audit makes that door a cheap, structured human decision instead of a silent
model guess. The observer theme recurs at every level: the content needs an external check,
the checker needs an external registry, and the *map of what is checkable* needs an observer
who knows what infrastructure exists.

## 10. From map to artifact: the `operationalize` skill and its ablation arc

The taxonomy was packaged as an agent skill (`plugins/belief-gate/skills/operationalize/`):
route every claim through the 5 classes, and always declare **CHECK** (what decides *this*
question) and **ASSUMES** (what infrastructure you presumed exists). Then we tested it the way
the program tests everything — trying to kill it. The arc, in order:

1. **Harness ablation** (deepseek, 14 planted tasks × 2 arms): headline **null** — a
   calibrated model *given an escape hatch* already commits none of the failures. Real effect
   at fine grain: the skill shifted S_spec behavior from answer-under-assumption to
   block-and-ask (2/5 → 5/5). Methodological catch: **the escape hatch offered to both arms is
   itself a mini-intervention** — we measured skill-vs-(baseline+hatch), not skill-vs-nothing.
2. **Agent A/B, first data** (Codex, plugin on/off): both arms passed the batch-close test
   **by execution** — strong agents already verify-by-running. The skill's margin was the
   *kind* of declaration: flagging **the absence of the spec** ("no policy defines 'abnormal' —
   I assumed X") vs. silently naturalizing the assumption.
3. **Sharpened data** (generator self-verifies its teeth): the undeclared criterion now
   *changes the answer* — z-score flags 1 invoice, IQR/MAD flag 4, and a **R$ 2.13 invoice is
   statistically invisible to every criterion** while being the most business-obvious anomaly.
4. **The inversion (v0.2, n=1):** the protocol-following arm declared IQR, delivered IQR's
   list — and **missed the R$ 2.13** a free-exploring baseline caught. Procedural tunnel
   vision: *named my check, ran my check, done.* The program's own architectural rule
   ("structure helps the weak case and can cost on a strong explorer") recurring against its
   own artifact.
5. **The patch (v0.3):** trigger narrowed to the skill's regime; a one-clause **STEP BACK**
   rule ("what is your criterion structurally blind to — scan the extremes before closing");
   the tunnel-vision anti-pattern written in with the real R$ 2.13 example; honest-bounds
   updated with the skill's own regime map.
6. **Control contamination discovered:** the "without" arm **self-served the cached skill**
   mid-run (`Get-Content ...\0.2.0\SKILL.md`) — an installed plugin is consulted even when not
   invoked. The control arm must be *verified*, not assumed — the external-observer rule
   applying to the experiment itself.
7. **Clean tally** (the R$ 2.13 catch): **baseline 2/4** — and, more telling, **four different
   methodologies in four runs** (IQR+percentiles / IQR-only / IQR-only / IQR+10%-of-median):
   free exploration *resamples the methodology every execution*. **v0.3: 2/2**, both catches
   textually traceable to the STEP BACK rule, **zero silent errors** — at the cost, once, of
   ~5 extra flags when the model mechanized the scan as a hard P05/P95 criterion (the catch/FA
   law surfacing *inside* the fix; every extra flag shipped its declared reason, so the cost is
   auditable, never silent). A composition bonus appeared unprompted: the agent ran the
   belief-gate completeness check first and **epistemically scoped the anomaly report** ("the
   anomaly list cannot be certified complete — the lot is missing 2 invoices").

**The claim that survives, in its final form:**

> Without the skill you get **a different analyst every run** — sometimes brilliant, sometimes
> blind, never predictable. With it you get **the same analyst every run**: a guaranteed floor
> (never a silent miss), declared assumptions, auditable errors. The skill buys the **floor and
> reproducibility, not the ceiling** — and per Norman's warning that reliability ≠ validity,
> this is reproducibility *with declared assumptions*, the auditable kind.

Statistical honesty: n is tiny on both sides (2/4 is a coin; 2/2 proves no rate). The support
is the **mechanism visible in transcripts** — v0.3's catches quote the rule; the baseline's
catches are ad-hoc inventions that differ every round.

---

*One line. About three-quarters of real decisions can be handed to code or execution today, a
third of what remains is just unwritten contracts, and the true semantic residue (~15%) cannot
be routed deterministically — but its failure modes are few, named, and forced into the open by
one declaration discipline: say what check decides it, and say what you assumed exists. Packaged
as a skill and ablated against a real agent, that discipline buys exactly what discipline can
buy: not a higher ceiling, but a floor — the same analyst every run, wrong only out loud.*
