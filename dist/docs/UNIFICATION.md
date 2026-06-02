# The Coherence Arrow: a unifying principle for trustworthy LLM systems

**Status:** Study / synthesis. This document connects three independently-developed
ideas — the belief-gate (this repo, measured), deterministic n-gram extraction
(Granville's Alt-DNN / RBF, external), and modality-preserving agent memory
(the "missing arrow" critique of AI-memory tools, external) — into a single
principle. The belief-gate parts are empirical; the cross-domain claims are
argued, and the central hypothesis is explicitly flagged as untested.

---

## 1. The one claim

> **A derived view — an answer, an extraction, a memory — is trustworthy only if it
> carries an arrow back to the source that produced it. Most LLM systems break
> precisely because the LLM, while compressing / judging / extracting, erases the
> arrow.**

This is cache coherence (distributed-systems literature, ~40 years old) applied to
cognition. A cache entry derived from a source of truth can only be trusted if there
is an *invalidation arrow* back to that source. An LLM that compresses "we *could*
refresh the TTL" into the flat fact "TTL refreshed" has produced a cache entry whose
arrow is gone: the recall path cannot tell a hedge from a decision, and the agent
acts on a fabrication. The same erasure happens when an LLM judges "the context
looks complete" (it cannot point to which required item is missing) or extracts a
value by loose regex (it cannot say which source token it came from, or with what
confidence).

The fix, in every case, is the same shape: **stop asking the LLM to compress or
judge the critical property; force a structured declaration whose arrow to the
source is preserved and checkable.**

---

## 2. Three instances of the same operation

| Instance | Critical property | What the LLM does wrong | The structural anchor (the arrow) |
| :--- | :--- | :--- | :--- |
| **belief-gate** (measured) | "Do I have the complete information the task needs?" | Judges completeness in-head; false-passes 7/15 on subtle gaps, model-dependent | `required − present` set difference / deletion-proof invariant. The arrow is `missing=[210]`: this answer depends on item 210, absent from the source. |
| **Deterministic extraction** (Alt-DNN, Lesson A) | "Is this datum present in the surface text?" | LLM-written regex is brittle; loose matching across noisy layouts | Stemmed multi-tokens + nested hashes; each match carries `f(x)` + a relevance grade — the arrow is "this came from this corpus token, this confidence." |
| **Coherent memory** (the missing arrow) | "Is this remembered fact a decision, an option, or a hypothesis?" | Lossy compression collapses modal status: "could" → "did" | A modality tag + provenance back-pointer + supersedes + TTL + invalidation hook + surfaced confidence. The arrow is literal: every fact points back to its source and can be invalidated. |

All three are the same move: **replace compression/judgment of a critical property
with a structured, source-anchored declaration that a deterministic checker can
verify.** This is the project's running thesis ("move determinism out of the LLM,
one step at a time") recognized in three independent domains.

---

## 3. The three layers form one pipeline

Stacked, the three are not competing ideas — they are three layers of one
trustworthy cognitive pipeline, each covering what the others do not:

```
   SOURCE  (database, document, API, prior turns)
        │
        ▼
   [1] EXTRACTION        ← deterministic multi-token / hash (Alt-DNN, Lesson A)
        │                  "what is actually present, robust to surface noise"
        ▼
   [2] VERIFICATION      ← belief-gate: set difference / coverage proof
        │                  "do I have everything the task requires? (never false-completes)"
        ▼
   [3] MEMORY            ← modality + provenance + invalidation (the missing arrow)
        │                  "what did I learn, and can the recall path trust it?"
        ▼
   ACTION
```

The empirical punchline that links them: **the three real benchmarks where the
belief-gate only tied or placed mid-pack did not fail at layer [2].** They failed at
layer [1] — the LLM-regex extractor produced an empty or mismatched `present` set
(long near-identical financial headers; an unparsed list). The belief-gate core was
flawless throughout (15/15 unit tests, leak-proof). **Layer [1] is the measured
bottleneck, and deterministic extraction is exactly its fix.** Layer [3] is the
layer we have not built at all.

So the two "distractions" are not distractions; they are the missing layers of the
same system, identified from outside and arriving exactly where the data said the
gaps were.

---

## 4. The coherence arrow, read backward into the gate

The memory critique supplies the unifying vocabulary, and it applies retroactively:

- **belief-gate already has the arrow.** `missing=[210]` *is* an arrow back to the
  source: "this answer is derived from item 210, which the source does not contain."
  The guarantee "never false-completes" *is* cache coherence: COMPLETE is certified
  only when the derivation (the answer) traces fully back to the source (every
  required item present). INCOMPLETE/UNDECIDABLE are honest invalidations.
- **belief-gate already has one of the six memory fields.** The
  COMPLETE / INCOMPLETE / UNDECIDABLE verdict is a *modality tag* — it refuses to
  collapse "proven" with "don't know," which is exactly the "could vs did" the memory
  tools lose. The other five (provenance, supersedes, TTL, invalidation hook,
  surfaced confidence) are what extend the same discipline to persistent memory.

This is why the unification is not forced: the gate is already a coherence mechanism
for the *answer* derivation. Generalizing it means installing the same arrow at the
extraction layer (below) and the memory layer (above).

---

## 5. The central hypothesis (untested — the thing to resolve before building)

There is a real tension that decides whether the unification is sound or hand-wavy:

> **The gate's guarantee is HARD; memory's looks SOFT.** Set difference is a
> mathematical proof — the gate cannot false-complete. But preserving "could vs did"
> seems to depend on *reading modality correctly from text*, which is judgment again
> — the very thing we are trying to remove.

**Hypothesis: it is the same problem as layer [1], and has the same solution.**

You do not ask the LLM to "compress what matters" (which erases modality). You force
a structured emission where modality is a *required field*, not prose — exactly as
the belief-gate forces `required = set(...)` instead of "judge completeness," and
exactly as deterministic extraction forces a normalized token instead of free regex.
The LLM still reads the text, but it must commit modality into a slot the schema
defines; the checker then enforces coherence rules over that slot (a fact tagged
`option` may never be acted on as `decision`; a `supersedes` edge invalidates the
older row deterministically). The reading is still imperfect — but it is *checkable
and bounded*, the same way a declared coverage claim is checkable even when the LLM
mis-declares (and the repair loop recovers it).

If this hypothesis holds, the three layers collapse to a single principle:

> **Replace compression and judgment with structured declaration plus deterministic
> checking. The LLM may populate the structure imperfectly; the structure, and the
> checker over it, carry the coherence arrow the LLM would otherwise erase.**

If it fails — if modality genuinely cannot be bounded into a checkable slot — then
layer [3] is a different, harder problem, and the unification stops at layers [1]+[2].
Resolving this is the next study, before any memory code.

---

## 5b. The hypothesis tested — and partly refuted (modality_20260602_111900)

Code: `bench/modality/`. Controlled dataset of 30 statements with ground-truth
modality (decision/option/hypothesis), three pipelines, deepseek-v4-flash. Primary
metric: UPWARD-INVERSION (a hedge recalled as a decision — the dangerous error).

```
method                accuracy   UPWARD-INVERSION
lossy (compress→class)  26/30        3/30
structured (slot)       27/30        3/30    ← ~identical to lossy
deterministic_check     29/30        0/30    ← rule-based (caveat below)
```

**The strong §5 hypothesis is REFUTED.** Forcing the LLM to emit modality as a
required slot did NOT beat lossy compression: structured ≈ lossy on both accuracy
and the dangerous inversion. The two methods even agreed on the same errors (e.g.
"pode ser mais rápido" and "é possível que… melhore" → both read `hypothesis` as
`option`). The problem was never that compression erased modality; it is that the
LLM *reads modality imperfectly*, and it reads it imperfectly the same way whether
you ask for a slot or a compressed fact. Structure relocated the errors; it did not
remove them.

**A different, possibly stronger reading survives.** The deterministic rule on
surface markers scored 29/30 with ZERO upward-inversions — beating both LLM
pipelines and, crucially, never committing the dangerous error. Caveat: the dataset
was generated from templates whose markers the rule knows, so this is *suggestive,
not proven* (circular by construction). But it points somewhere real: modality lives
in surface markers ("vamos" / "poderíamos" / "talvez"), and a classifier that keys
on them distinguishes cases the LLM conflates. The conflation the LLM makes is
hypothesis↔option (a genuinely subtle epistemic/deontic line), not the dangerous
hypothesis↔decision — but it still mis-commits sometimes, and the rule does not.

**What this does to the unification.** Layer [3] does NOT reduce to "make the LLM
declare modality" — that is just judgment again, and it fails the same way layer [1]
fails with LLM-regex. It reduces to the SAME fix as layer [1] and [2]: **take the
decision away from the LLM and put it in a deterministic check over surface form.**
So the coherence-arrow principle SURVIVES and is in fact reinforced — but the
specific §5 mechanism (LLM-emitted structured declaration) is refuted. The arrow is
installed by a deterministic classifier, not by asking the model nicely.

### 5c. Decisive test on real text — DETERMINISTIC modality refuted, but the structured slot survives (modalityreal_20260602_134919)

Code: `bench/modality/harness_real.py`, `classifiers.py`. A generator LLM produced
30 natural, marker-avoiding statements (judge-confirmed ground truth). Six deciders;
the two deterministic classifiers (RBF kernel à la Granville, and a small logistic)
were trained ONLY on the templated easy text and tested on this real varied text —
a true generalization test.

```
decider          coverage   acc/covered   UPWARD-INVERSION (dangerous)
structured (LLM)   30/30       30/30          0/30      ← won, clean
lossy (LLM)        29/30       28/29          0/30
frozen_lexicon      8/30        8/8           0/30      (safe but ~no coverage)
rbf_proto          30/30       19/30          3/30
small_clf          30/30       19/30          9/30      (worst — 9 dangerous inversions)
rbf_abstain         0/30         —            0/30      (margins collapsed to ~0; see below)
```

**Every deterministic mechanism lost; the LLM won.** structured scored 30/30 with
zero dangerous inversions. The RBF kernel — which looked promising on 8 hand-picked
sentences in the offline preview — got only 19/30 on unbiased generated text and
made 3 upward-inversions; the small logistic made 9. The frozen lexicon covered
8/30. The RBF abstain-gate abstained on ALL 30, because its calibrated margin (p25
of training = 0.98) dwarfed real-text margins (0.0–0.04): the kernel has no genuine
confidence on text that doesn't resemble its prototypes, and the margin honestly
reflects that. The offline preview was misleading because **I** had picked the 8
sentences; the generated set was not cherry-picked, and it reversed the result.

**Why, in the cases:** "No índice que removemos ontem, mora a lentidão" (hypothesis)
→ RBF: decision (dangerous); "A correlação… sugere vazamento" (hypothesis) → RBF:
option. Lexical similarity ("removemos"/"removida") pulls toward the wrong modality.
The classifiers capture surface similarity, not intent.

### The final conclusion (after four refutations)

| mechanism for modality | result |
| :--- | :--- |
| LLM declares in a slot (§5 strong) | does not preserve (≈ lossy) — refuted |
| frozen marker lexicon (§5b) | 0–8/30 coverage on real text — refuted |
| RBF kernel over embeddings (§5c) | 19/30, 3 inversions, margins collapse — refuted |
| small logistic over embeddings | 19/30, 9 dangerous inversions — worst |
| **LLM (lossy / structured)** | **0 inversions, 28–30/30 — best** |

> **Modality has no DETERMINISTIC anchor, but the structured slot is the cure.**
> Unlike completeness (an enumerable key) and presence (a string/hash match), modality
> cannot be recovered by a deterministic checker — every such mechanism (lexicon, RBF,
> logistic) either fails to cover or commits the dangerous error more than the LLM, so
> there is no CPU *verifier* of a modal value. BUT the structured LLM slot
> (`structured`: 30/30, 0 dangerous inversions) decisively beats both free compression
> and every deterministic decider — and it is exactly the fix the source's full
> writeup left as an open question (§5d). So the right conclusion is not "the LLM is
> unavoidable, give up"; it is "the arrow for modality is a structured declaration the
> LLM fills, with no independent verifier — present, but without teeth."

### What this does to the unification — reconciled with the full source (5d)

The full version of the "missing arrow" writeup (Harrison Guo, *Agent Memory Is a
Cache Coherence Problem*, 2026-05-28) sharpens this, and it revises our earlier
"layer [3] has no arrow" conclusion. Two things the full text makes precise:

**(a) The failure is SCHEMA-induced, not "LLMs can't read modality."** claude-mem
compressed via Haiku into a `facts[]` array *with no modality field*. The hedge was
flattened because there was nowhere to store "could" — the model was never asked to
tag modality; the schema couldn't hold it. His exact open question (verbatim): "you'd
need to compress into a richer schema (with `kind: decision|option|question`) … and
you'd need the compression model to reliably tag the modality. Haiku 4.5 didn't tag
it. **Whether a more careful prompt or schema would is an open question.**"

**(b) Our §5c experiment answers that open question — affirmatively.** Our
`structured` arm IS his proposed fix: force the LLM to emit modality as a required
slot. Result: **30/30 accuracy, 0 dangerous inversions** (N=30, vs his N=1). A
schema WITH a modality slot, filled by the LLM, preserves modality; a slot-LESS
schema (claude-mem) loses it. This also explains why our `lossy` arm did not
replicate his inversion: ours compressed to free text and *re-classified* modality
downstream, so surface markers survived; his schema killed modality at write with no
recovery path. We did not faithfully reproduce his failure — but our `structured`
arm reproduces (and validates) his proposed cure.

**The corrected picture: layer [3] DOES get an arrow — a softer one.** Split the
memory schema by property type:

| field | anchor | arrow |
| :--- | :--- | :--- |
| provenance, supersedes, TTL, invalidation, confidence | timestamps, IDs, source pointers — deterministic bookkeeping | **hard** (CPU-verified, like [1]/[2]) |
| **modality** | no deterministic checker (§5c: lexicon/RBF/logistic all lose) — but a structured slot the LLM fills (§5c: structured 30/30) | **soft** (LLM-declared, not CPU-verified, yet far better than free compression) |

So the unification extends to [3] after all, with one qualification: for the five
bookkeeping fields the arrow is the same hard, deterministic kind as completeness and
presence; for *modality* the arrow is a structured declaration the LLM populates and
is trusted on — there is no independent deterministic verifier (we proved every
candidate loses), but the structured slot is itself the coherence mechanism, and it
measurably beats the slot-less compression that current tools ship.

This is the project's recurring move once more — **replace free compression/judgment
with a structured declaration** — and it works for modality too. The only thing that
does NOT generalize from [1]/[2] is the independent *checker*: completeness and
presence get a CPU verifier; modality gets a slot but no verifier. The arrow is
present in all three layers; its *teeth* (deterministic verification) are present in
two.

### The two-axis frame (worth importing)

The full writeup's central frame is also worth adopting: memory varies on two
independent axes — **fidelity** (lossless/lossy) × **retrieval** (exact/approximate)
— not one. belief-gate lives at lossless+exact: it verifies against the actual source
rather than a compressed view. A RAG pipeline the gate wraps is lossy+approximate.
Seen this way, the gate is a device that re-installs the *exact* property onto
approximate retrieval: it refuses to answer unless the required items are exactly
present, which is the lossless+exact discipline applied at query time. The coherence
arrow is what links the two axes — an exact, lossless check is precisely a view that
keeps an arrow to its source.

## 6. What each layer would need to be built

Concrete, in priority order by risk-adjusted value:

### Layer [1] — deterministic extraction (lowest risk, immediate payoff)
- Replace the LLM-regex `present`-extractor with normalized multi-token matching:
  stem + lowercase + collapse punctuation, then exact-match required keys against a
  hash of context tokens. No model in the decision path.
- Re-run the keyed-aggregation benchmark with this extractor. Prediction: the 7
  over-abstain (empty `present`) and 2 false-sufficient (header mismatch) largely
  vanish, turning the mid-pack tie into an *honest* win — honest because it comes
  from fixing the correct layer, not from cherry-picking the regime.
- This also discharges the lib README's load-bearing rule with a reference
  implementation: "feed `present` from a deterministic source."

### Layer [2] — verification (done; the stable center)
- belief-gate as it stands: `check_set`, `verify_coverage`, the repair loop, the
  three-verdict modality. 15/15 tests, leak-proof, cross-model 0/15. Nothing to add
  for the core; it is the fixed point the other layers attach to.

### Layer [3] — coherent memory (different problem; §5 refuted, see §5c)
- The structural fields from the critique are still worth building — `provenance`,
  `supersedes`, `ttl_class`, `invalidation_hook`, `confidence` are deterministic
  bookkeeping with real value (these are NOT semantic; they have anchors).
- But `modality` (decision/option/hypothesis) is **not** recoverable by a
  deterministic checker over surface form — §5c measured every such mechanism
  (lexicon, RBF kernel, logistic) lose to the LLM. The best modality decider is an
  LLM forced into a structured slot; it is better than free compression but remains
  a probabilistic judgment, not a proof.
- So layer [3] splits: the **bookkeeping** fields get the coherence arrow
  deterministically; the **modal status** field does not, and stays an LLM judgment
  (with the structured-slot improvement as the available best practice).

---

## 7. What this is, honestly

- **Proven:** layer [2] (the gate). The real-benchmark gaps were at layer [1]
  (extraction), not [2]. The arrow framing of the gate's existing guarantee is a
  re-description of measured behavior.
- **Measured and supported:** completeness and presence have deterministic anchors
  (set difference, string/hash match) — the arrow installs there.
- **Conjectured, then split by the data (§5 → §5c → §5d):** "modality reduces to a
  *deterministic* checker" is REFUTED — lexicon, RBF, logistic all lose to the LLM on
  real text. But "modality is preserved by a *structured slot the LLM fills*" is
  SUPPORTED (structured: 30/30, 0 dangerous inversions), and that is exactly the fix
  the source's full writeup posed as an open question. So modality has an arrow
  (structured declaration) but no independent verifier (no CPU checker).
- **The unification covers all three layers — with one graded distinction:** the
  arrow (structured declaration replacing free compression/judgment) is present in
  [1], [2], and [3]; the deterministic *verifier* of that declaration is present in
  [1] and [2] (string/hash match, set difference) and absent for the modality field
  of [3] (no checker beats the LLM). Arrow in three; teeth in two.

The honest contribution, stated with that distinction:

> **Trustworthy LLM cognition is cache coherence: every derived view — an extraction,
> a verification, a memory — needs a structured declaration with an arrow back to its
> source, replacing free LLM compression/judgment. For properties with a structural
> anchor (completeness → set difference, presence → string match, and the bookkeeping
> fields of memory → provenance/supersedes/TTL) the arrow has TEETH: a deterministic
> checker verifies it. For genuinely semantic properties (modal status: decision vs
> hedge) the arrow is a structured slot the LLM fills — measurably better than the
> slot-less compression current memory tools ship, but without an independent
> verifier. The contribution is knowing which properties get teeth and which only get
> the slot.**

That last clause is the real result of the whole real-benchmark + memory study: a
*criterion* for when the gate-REPL discipline applies (anchorable property,
structured present, task-derived required) and when it does not (semantic property,
open relevance, intent-laden modality) — established by honest elimination rather
than asserted.

---

## 8. Notes on the Alt-DNN source (scope of what was borrowed)

Only Lesson A (deterministic multi-token extraction) is taken, and only the classical
IR core of it (stemmed n-grams + nested hashes), which is sound and directly fixes
the measured layer-[1] bottleneck. The paper's RBF/Gaussian-mixture machinery,
training-free interpolation, and "96% vs 30–55%" comparison are **not** adopted: the
accuracy claim compares a corpus-specialized SLM to generic LLMs (apples/oranges),
and the rest is unverified here. Three of the four "lessons" a prior analysis drew
from it are rejected on principle:
- **Kernel relevance grades replacing PASS/FAIL** would reintroduce probabilistic
  judgment into the *decision* and break the never-false-complete guarantee. Fuzzy
  matching belongs in extraction (resolving "Store_A" vs "Loja A" *before* the set is
  formed), never in the completeness verdict.
- **Weighted θ-matrix predicates** make the coverage proof *less* auditable, against
  the checkability principle; our predicate result showed robustness comes from
  simple deletion-proof invariants (count, contiguity), not weights.
- **Per-domain MoE namespaces** are harmless and cheap (a `required` set can be
  scoped) but marginal — kept as an option, not a layer.
