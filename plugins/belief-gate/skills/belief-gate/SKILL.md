---
name: belief-gate
description: >-
  Use BEFORE answering any question that requires grounding in retrieved or
  provided context (RAG results, pasted documents, query outputs, multi-file
  data). Verifies — by EXECUTING code, not by eyeballing — that the context
  actually contains every item the task needs, then either abstains with the
  exact missing list or proceeds to compute. Use whenever a wrong answer would
  be worse than "I don't have enough data", or when the context might be
  incomplete (top-k retrieval, truncated dumps, partial exports).
---

# Belief Gate: verify completeness by execution, then answer

## The problem this prevents

When you answer from retrieved or pasted context, you tend to treat that context
as if it were complete. When it isn't, you produce a confident wrong answer over
incomplete data — a **confabulation**. Worse, if you also do arithmetic on the
incomplete data, the wrong number looks *authoritative* (it has decimals, it
looks computed).

Eyeballing completeness fails in a specific, measurable way: you reason at
**range/summary granularity** ("IDs 300–320 look present") and miss **interior
holes** (ID 310 is actually absent). The fix is to stop judging and start
**executing**: the requirement is a set, the context is a set, the gap is a set
difference — and a set difference cannot miss an interior element.

## The rule

> **Completeness is computation, not judgment. Compute it; do not estimate it.**

Do NOT decide "does this look complete?" in your head. Instead:

1. **DECLARE** what the task requires, as a concrete data structure (a set of
   keys/IDs, a list of required fields, etc.). This is the one step that needs
   your language understanding.
2. **VERIFY by execution**: write and RUN code that extracts what the context
   actually contains and computes `required − present`. The code decides, not you.
3. **GATE on the result**:
   - If the gap is non-empty → **abstain**. State exactly what's missing. Do not
     guess, interpolate, or "assume zero" for missing items.
   - If the gap is empty → **proceed**, and do the actual work (compute / answer)
     in code too where the work is deterministic (sums, joins, counts, lookups).

## How to apply it

### Step 1 — Declare the requirement (your job: language → structure)

Read the task and write down, as code, the exact set of things it needs. Examples:

```python
# "tax on store A IDs 200-250 and store B IDs 400-450"
required_A = set(range(200, 251))   # inclusive
required_B = set(range(400, 451))
rates = {"A": 0.08, "B": 0.12}
```

```python
# "summarize the Q3 figures for all five regions"
required_regions = {"North", "South", "East", "West", "Central"}
```

```python
# "reconcile invoices INV-100 through INV-120"
required_invoices = {f"INV-{n}" for n in range(100, 121)}
```

Be careful with boundaries ("inclusive", "through", "up to but not including").
A range-translation off-by-one is now your only failure mode — and it is easy to
double-check, unlike judging completeness.

### Step 2 — Verify by executing a set difference

Put the context in a variable and RUN code that parses what's present and diffs
it against the requirement. Run it with your code tool (Bash/python). Do not
simulate the output in your head.

```python
import re

context = """<<paste or reference the retrieved/provided context here>>"""

# extract what's actually present (adapt the pattern to your data)
present_A = set(int(m) for m in re.findall(r"loja_A.*?ID_(\d+)", context, re.S))
present_B = set(int(m) for m in re.findall(r"loja_B.*?ID_(\d+)", context, re.S))

gap_A = sorted(required_A - present_A)
gap_B = sorted(required_B - present_B)

if gap_A or gap_B:
    print(f"GATE: FAIL  missing_A={gap_A}  missing_B={gap_B}")
else:
    print("GATE: PASS")
```

The general shape, whatever the domain:

```python
present = extract_present_keys(context)     # parse, don't guess
gap = required - present                     # set difference
print("GATE: FAIL", sorted(gap)) if gap else print("GATE: PASS")
```

### Step 3 — Gate on the executed result

- **GATE: FAIL** → Tell the user you cannot answer completely, and report the
  exact missing items from the code output. Example:
  > I can't compute this reliably — the context is missing store B IDs 410 and
  > 411. With those I can finish; right now any total would be wrong.

  Never fill the hole. "Assume 0", "interpolate", "use the average" all silently
  corrupt the answer.

- **GATE: PASS** → Proceed. If the remaining work is deterministic (summing,
  joining, counting), do THAT in code too — same principle: don't compute in your
  head what the CPU can compute exactly.

```python
# gate passed: compute the actual answer by execution
vals_A = {i: v for i, v in parsed_A.items() if i in required_A}
vals_B = {i: v for i, v in parsed_B.items() if i in required_B}
total = sum(v * rates["A"] for v in vals_A.values()) \
      + sum(v * rates["B"] for v in vals_B.values())
print(f"FINAL: {total}")
```

## When to use vs skip

**Use it when:**
- The context comes from retrieval (RAG / top-k), a truncated dump, a partial
  export, or any source that might not be complete.
- The task needs *all* of a known set (every region, every invoice, an ID range).
- A confidently wrong answer is worse than an honest "insufficient data".

**Skip it when:**
- The full source is obviously, completely present and small.
- The task is open-ended generation with no completeness requirement.
- There is no well-defined "required set" to diff against.

## Why this works (one line)

A set difference cannot miss an interior element, but human/LLM range-judgment
routinely does. Moving the completeness check from judgment to execution turns an
unreliable "looks complete" into a deterministic "these exact items are missing".

## Anti-patterns (do NOT do these)

- ❌ "The context appears to contain the full range, so I'll proceed." (eyeballing)
- ❌ Filling a missing item with 0, an average, or an interpolation.
- ❌ Doing the completeness check OR the final arithmetic in your head when the
  data is right there to be parsed and computed exactly.
- ❌ Declaring the required set loosely ("the relevant IDs") instead of concretely
  (`set(range(200, 251))`).
