---
name: operationalize
description: >-
  Use for HIGH-STAKES verification: closing a batch/report, claiming
  done/complete/verified, build-loop termination, or any task where a
  spec/threshold/policy the task needs is not stated. Routes the claim through
  a 5-class taxonomy (checkable-now / needs-execution / needs-waiting /
  under-specified / genuine-judgment) and forces the declarations — the CHECK
  that decides it and the ASSUMES it depends on. Prevents the two measured
  failure modes: silently inventing a missing spec and substituting a proxy
  check that answers an easier question. In OPEN EXPLORATORY analysis, apply
  the declarations but do NOT let the named check end the exploration — the
  declared criterion is a floor, not a ceiling.
---

# Operationalize: route the claim, name the check, declare the assumption

## The problem this prevents (measured)

When an agent needs to verify something, it fails in two specific, measured ways
(30% of semantic decisions in our router study, all silent):

1. **Silent spec-assumption.** The task says "flag abnormal payroll variance" — no threshold
   is defined anywhere. The agent invents one ("check if delta exceeds the pre-defined
   threshold" — defined by *whom*?) and proceeds as if the check were real.
2. **Proxy-check substitution.** The question is "is this documentation semantically
   outdated?" and the agent checks *file timestamps* — a decidable check that answers a
   *different, easier* question, then reports the original one as verified.

Both produce the worst artifact: **a confident verification of the wrong thing.** Forcing the
declarations below cut the silent version of these errors by ~83% in testing.

## The protocol

Before relying on, asserting, or verifying ANY claim ("done", "complete", "correct",
"exists", "matches"), classify it and act accordingly:

| class | meaning | what YOU do |
| :--- | :--- | :--- |
| **D** — decidable now | a deterministic check against an available source settles it | **run the check now** (set difference, lookup, date compare — see the `belief-gate` skill for the core moves). Do not eyeball what code can decide. |
| **OE** — needs execution | settled by running something (build, test, benchmark, staging, play-mode) | **execute and observe.** Never predict what execution would show — run it. |
| **OW** — needs waiting | settled by a real-world consequence later (a metric next cycle, a ruling) | say plainly the answer is **pending**; state what outcome will settle it. Do not claim it now. |
| **S_spec** — under-specified | looks semantic only because no contract/threshold/policy was written | **DO NOT silently assume the spec.** Surface it: *"'abnormal' has no defined threshold — I'll use 5% unless you say otherwise"* or propose the checklist/manifest. Writing the spec converts this to D/OE. |
| **S_core** — genuine judgment | interpretation, preference, quality, values | give your view **labeled as judgment**, never as verification. "I think X (opinion, not checked)". |

With the classification, always produce the two declarations:

- **CHECK:** the named check that decides **this exact question** — not a proxy for it.
  Test: would this check still say "yes" while the actual question's answer is "no"?
  If yes, it is a proxy — name a real one or downgrade the class.
- **ASSUMES:** every piece of infrastructure/policy/data you assumed exists (a threshold,
  a registry, a DMS, a policy table). If the check is impossible without an unwritten
  spec, the class is S_spec — say so and surface it.
- **STEP BACK (after the check runs):** ask once — *what is my declared criterion
  structurally blind to?* — and do one quick common-sense scan of the extremes/oddities
  before closing. The named check is your **floor, not your ceiling**: running it does not
  end the noticing.

## Worked examples

- "All 20 invoices in the batch present?" → **D**. CHECK: `set(range from cover) −
  set(ids in export)`. ASSUMES: the cover sheet's declared range is authoritative. → run it.
- "Does this endpoint break on an empty payload?" → **OE**. CHECK: execute the request with
  an empty payload, observe. → run it, don't reason about it.
- "Is this month's payroll variance abnormal?" → **S_spec**. No threshold exists. → *"No
  definition of 'abnormal' exists — propose: flag any line-item delta >5% MoM. Confirm?"*
- "Is this variable name clear?" → **S_core**. → "I'd rename it (judgment); there is no
  check that decides clarity."
- "Is the doc outdated relative to the code?" → **S_core** (mostly). Timestamps are a
  **proxy** — a doc edited yesterday can still describe last year's behavior. Say what a
  human must read; check the decidable slivers (doctests) separately.

## Anti-patterns (each one was observed in testing)

- ❌ Inventing the missing threshold/policy/registry and proceeding ("pre-defined threshold"
  that nobody pre-defined). Surface it instead — this is the #1 measured failure.
- ❌ Proxy checks: verifying an easier neighboring question and reporting the hard one as
  done (timestamps for semantic staleness; "consult the statute" for legal conformity).
- ❌ **Smuggling semantics inside the check's wording**: "search the contract for the clause
  *or synonyms with equivalent legal meaning*" — reads like a grep; "equivalent legal
  meaning" is not a grep. If the check's description contains an interpretive step, the
  class is not D.
- ❌ Saying "verified" when you checked *existence* only (a case exists ≠ it supports the
  claim; a file exists ≠ its content is right).
- ❌ Predicting execution results instead of executing ("this test would pass").
- ❌ **Letting the declared check END the analysis** (procedural tunnel vision). Observed:
  an agent declared IQR, reported IQR's 4 outliers — and missed the R$ 2.13 invoice that
  any accountant flags first, because IQR's lower fence was negative. Your criterion's
  blind spots are still your job.

## Honest bounds

- This routing is itself a semantic judgment — measured at judge-grade reliability
  (kappa ≈ 0.46–0.49): solid at the extremes (checkable vs judgment), fuzzy at the borders
  (D vs OE; S_spec vs S_core). **Bias to the safe side**: when unsure between D and S_spec,
  choose S_spec and surface the assumption — the cost is a question; the alternative is a
  fake gate.
- The D/S_spec boundary is **observer-relative**: it depends on what infrastructure you KNOW
  exists. That is exactly why ASSUMES is mandatory — it makes your world-model auditable.
- Declaring does not eliminate the judgment; it makes your errors **visible and cheap to
  audit**. That is the guarantee: no *silent* wrong verification.
- **This discipline has a regime.** Measured: it pays most where discipline is missing
  (routing decisions, weaker models, long sessions, high-stakes closes). On a strong agent
  doing open exploration it can *narrow* attention (observed once: the protocol-following
  arm missed a business-obvious anomaly a free explorer caught). Hence the STEP BACK rule —
  and if the task IS exploration, keep exploring past your named check.
