"""Predicate-defined coverage: completeness when the requirement is a PREDICATE.

Many tasks define the requirement by a predicate ("all sales > 5000") rather than
an enumerable set. There is no a-priori set to diff against; completeness becomes
a COVERAGE question: "have I seen every record the predicate could select?"

The central, hard-won lesson encoded here:

  * Coverage is decidable only under a DELETION-PROOF invariant on the source.
  * full_count (count == claimed source total) and contiguous_ids (keys form a
    full range) ARE deletion-proof.
  * sorted_to_threshold (the list is sorted and you crossed the boundary) is NOT:
    a record deleted from the MIDDLE leaves the list sorted and the boundary
    crossed. Determinism over the wrong invariant fails as silently as judgment.

You declare WHICH invariant the source justifies (as a CoverageClaim) and the
library verifies two gates deterministically:
  (a) is the declared kind deletion-proof?
  (b) does it actually hold in the data?
COMPLETE only if both. The declarer (you, or an LLM you wrap) may err in either
direction and the gate never false-completes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import GateResult, Verdict


class CoverageKind(str, Enum):
    FULL_COUNT = "full_count"                  # source declares a total; all present
    CONTIGUOUS_IDS = "contiguous_ids"          # keys form a gapless range
    SORTED_TO_THRESHOLD = "sorted_to_threshold"  # sorted + boundary crossed (WEAK)
    NONE = "none"                              # no coverage invariant applies
    UNDECIDABLE = "undecidable"                # predicate not evaluable from records


# Only these two prove no qualifying record was deleted.
DELETION_PROOF = {CoverageKind.FULL_COUNT, CoverageKind.CONTIGUOUS_IDS}


@dataclass(frozen=True)
class CoverageClaim:
    """A declared coverage argument. `total` is the SOURCE's claimed record count
    (from its metadata/label) — NEVER the number of records you happen to see."""
    kind: CoverageKind
    total: int | None = None


@dataclass(frozen=True)
class SourceFacts:
    """Deterministic facts parsed from the context. You compute these from your
    own data; the library does not parse for you (it is domain-agnostic)."""
    present_count: int            # records actually present
    keys: list                    # the keys/ids present (for contiguity)
    sorted_desc: bool             # records sorted by the predicate's order key
    boundary_crossed: bool        # the sort passed the predicate threshold
    predicate_evaluable: bool     # can the predicate be evaluated from records at all?


def verify_coverage(claim: CoverageClaim, facts: SourceFacts) -> GateResult:
    """Two-gate validation: (a) deletion-proof kind? (b) holds in data?

    Returns COMPLETE only if both. UNDECIDABLE if the predicate can't be evaluated
    from the records (no invariant can rescue that). Otherwise INCOMPLETE.
    """
    # An unevaluable predicate is undecidable regardless of coverage.
    if not facts.predicate_evaluable:
        return GateResult(
            Verdict.UNDECIDABLE,
            reason="predicate cannot be evaluated from the records "
                   "(a needed field is absent / external)",
        )

    if claim.kind is CoverageKind.UNDECIDABLE:
        # Declaring undecidable is only valid when the predicate truly isn't
        # evaluable — but we just established it IS. So this is an undue claim.
        return GateResult(
            Verdict.INCOMPLETE,
            reason="declared undecidable, but the predicate is evaluable; "
                   "declare a coverage invariant instead",
        )

    deletion_proof = claim.kind in DELETION_PROOF
    holds = _claim_holds(claim, facts)

    if deletion_proof and holds:
        return GateResult(
            Verdict.COMPLETE,
            reason=f"coverage proven via {claim.kind.value}",
            detail={"kind": claim.kind.value},
        )
    if not deletion_proof:
        return GateResult(
            Verdict.INCOMPLETE,
            reason=f"'{claim.kind.value}' is not deletion-proof "
                   "(a mid-deleted record would be invisible)",
        )
    return GateResult(
        Verdict.INCOMPLETE,
        reason=f"'{claim.kind.value}' declared but does not hold in the data",
    )


def _claim_holds(claim: CoverageClaim, facts: SourceFacts) -> bool:
    if claim.kind is CoverageKind.FULL_COUNT:
        return claim.total is not None and facts.present_count == claim.total
    if claim.kind is CoverageKind.CONTIGUOUS_IDS:
        ks = facts.keys
        if not ks:
            return False
        try:
            contiguous = sorted(ks) == list(range(min(ks), max(ks) + 1))
        except TypeError:
            return False  # non-numeric keys can't be contiguous in this sense
        return contiguous and (claim.total is None or len(ks) == claim.total)
    if claim.kind is CoverageKind.SORTED_TO_THRESHOLD:
        return facts.sorted_desc and facts.boundary_crossed
    return False
