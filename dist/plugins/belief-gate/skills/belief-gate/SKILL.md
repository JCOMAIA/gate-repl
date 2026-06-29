---
name: belief-gate-legal
description: >-
  Use BEFORE presenting any legal answer that cites case law / jurisprudence
  (court decisions, precedents, súmulas, REsp/RE/ADI/Tema, US opinions). Verifies
  — by querying an authoritative registry, not by trusting the model — that every
  cited case ACTUALLY EXISTS, and abstains/flags fabricated ("phantom") citations.
  Guarantees existence only; it does NOT verify the holding or relevance (that is
  semantic — flag for a human). Use whenever a fabricated citation would be harmful
  (legal filings, advice, research memos).
---

# Belief Gate — Legal citations

This is the **belief-gate** mechanism (see the `belief-gate` skill for the core: *completeness
is computation, not judgment*) applied to one domain failure: **LLMs hallucinate case
citations** — they invent a precedent that does not exist, formatted convincingly. That exact
failure has gotten lawyers sanctioned.

The move is the core gate: don't *judge* whether a cited case is real — **look it up**.
`required` = the set of cases the answer cites. `present` = the cases that exist in an
authoritative registry. Any cited case **not** in the registry is a fabrication → block it.

## The hard boundary (read this first — it is half the job)

> **This verifies EXISTENCE, not CORRECTNESS.** It catches a *fabricated* case (one that does
> not exist). It does **NOT** catch a *real* case cited for the *wrong holding*, an *irrelevant*
> case, or a misquoted one. Those are *misselection* — semantic, not a lookup.

So two, and only two, verdicts per citation:
- 🔴 **NOT FOUND → fabrication.** Strip it / refuse to present it / abstain. Never present a
  citation you could not confirm exists.
- 🟡 **EXISTS ✓ → existence confirmed, nothing more.** Present it **with a disclaimer**: its
  *holding and relevance are not verified* — the human must read the source. Do not claim you
  "verified the case."

Claiming "I verified the citations" when you only confirmed existence is the over-claim this
skill exists to prevent.

## The sources (use these, honestly)

`present` must come from an **authoritative registry**, not from the model:

| source | jurisdiction | usable how |
| :--- | :--- | :--- |
| **DataJud / CNJ** (Base Nacional de Dados do Poder Judiciário) | Brazil | **public REST API** (Elasticsearch-style); usable from a backend with the public key |
| **STF / STJ / TJ portals** | Brazil | per-court search; scrape/automate carefully, respect ToS |
| **jusbrasil** | Brazil | **no public API** — only via your own authenticated access / a backend; not callable from a browser |
| **CourtListener (Free Law Project)** | US | **free REST API**, CORS-friendly |

Pick the registry that actually covers your jurisdiction. **Coverage is a caveat, not a
detail:** a real case absent from your registry will show as 🔴 — that is a *false fabrication
flag*, and it means your registry is incomplete, not that the case is fake. Choose an
authoritative, complete source and say which one you used.

## How to apply it

### Step 1 — Get the answer with citations as STRUCTURED data
Have the model answer, and emit its citations as a parseable list (not buried in prose), e.g.
ask it to end with `CITATIONS: ["REsp 1.234.567/SP", "Súmula 7/STJ"]`. Parsing prose with a
regex is a fallback, and the parser is the floor — a malformed citation matches badly.

### Step 2 — Verify each citation against the registry (the gate)
```python
cited = parse_citations(model_output)          # the answer's claimed cases
results = []
for c in cited:
    rec = registry_lookup(c)                    # <-- a REAL query: DataJud / CourtListener / etc.
    results.append((c, "EXISTS" if rec else "NOT_FOUND"))

fabricated = [c for c, s in results if s == "NOT_FOUND"]
print("GATE: FAIL  fabricated=", fabricated) if fabricated else print("GATE: PASS (existence)")
```
`registry_lookup` is the load-bearing piece: it must hit the authoritative source and match the
citation reliably (normalize court/number/year; matching is fuzzy — over-loose matching can
false-pass a fabrication, so prefer strict, structured matching).

### Step 3 — Gate on the result
- **Any NOT_FOUND** → do **not** present those citations. Tell the user plainly:
  > I removed 2 cited precedents I could not confirm exist in [registry] — presenting them would
  > risk citing a non-existent case. The remaining citations were confirmed to exist (their
  > holdings still need a human read).
- **All EXISTS** → present them, each tagged *existence confirmed; holding/relevance not
  verified*. Never upgrade that to "verified."

## When to use vs skip
- **Use it** whenever the output cites case law and a phantom citation would be harmful (filings,
  advice, memos). This is the regime where LLMs fabricate convincingly.
- **Skip the existence check** for non-citation legal text (general explanation, statute text you
  can quote from a trusted source) — but the moment a specific case/precedent is named, gate it.

## Anti-patterns (do NOT do these)
- ❌ Asking the model "does this case exist?" — that is the judgment you are replacing. **Look it
  up** in the registry.
- ❌ Presenting a citation you could not confirm exists ("it is probably real").
- ❌ Saying "I verified the cases" when you confirmed **existence** only. Existence ≠ correct
  holding ≠ relevance.
- ❌ Over-loose matching (e.g., matching by case number alone across courts) that lets a
  fabricated citation pass as a near-match. Match strict and structured.
- ❌ Using a registry that does not cover the jurisdiction and reading its misses as fabrications.

## One line
Turn *"did the model invent this precedent?"* from a judgment into a **lookup** — phantom
citations become impossible to present. What it cannot do — confirm a real case actually says
what the answer claims — stays with the human. Existence by code; meaning by a lawyer.
