"""Self-consistency repair loop — recovers declaration slips without losing safety.

When you wrap an LLM to declare a CoverageClaim, it can err two ways:
  * FORM slip: it puts the answer value into `total` instead of the record count.
  * JUDGMENT error: it declares `undecidable` for a predicate that IS evaluable.

`check_consistency` catches BOTH against the deterministic SourceFacts, returning a
diagnostic. `run_with_repair` feeds the diagnostic back to your declarer and retries.

Two non-negotiable invariants (encoded here, enforced by tests):
  1. The repair diagnostic NEVER suggests the answer derived from visible data.
     The correct `total` is the SOURCE's claimed total (from its label/metadata),
     not the count of records you happen to see — otherwise partial data would be
     "repaired" into a false COMPLETE.
  2. The loop only fixes the DECLARATION. The final verdict still comes from
     `verify_coverage`, which never false-completes. The loop can make the gate
     ANSWER more decidable tasks; it can never make it certify an incomplete one.

The LLM is plugged in by you via `declare_fn`; the library stays SDK-agnostic.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .coverage import (CoverageClaim, CoverageKind, DELETION_PROOF, SourceFacts,
                       verify_coverage)
from .types import GateResult


# declare_fn(facts, source_total, repair_message) -> CoverageClaim
# - facts:        the deterministic SourceFacts
# - source_total: the total the SOURCE claims (from its label), or None
# - repair_message: "" on the first try, else the diagnostic to fix
DeclareFn = Callable[[SourceFacts, "int | None", str], CoverageClaim]


@dataclass(frozen=True)
class Consistency:
    coherent: bool
    diagnostic: str = ""


def check_consistency(claim: CoverageClaim, facts: SourceFacts,
                      source_total: int | None) -> Consistency:
    """Generic coherence check of a declared claim against deterministic facts.
    Does NOT decide completeness — only flags a declaration that cannot be
    reconciled, so the declarer can fix it."""
    k = claim.kind

    # JUDGMENT error: undue undecidable.
    if k is CoverageKind.UNDECIDABLE and facts.predicate_evaluable:
        return Consistency(False,
            "declared 'undecidable', but the predicate IS evaluable from the "
            "present records; declare a coverage invariant (full_count / "
            "contiguous_ids) instead.")

    if k is CoverageKind.FULL_COUNT:
        if claim.total is None:
            return Consistency(False,
                "kind 'full_count' requires a total: the SOURCE's claimed record "
                "count (from its label), not a value or sum.")
        # FORM slip: total below what you already see is impossible.
        if claim.total < facts.present_count:
            return Consistency(False,
                f"total={claim.total} is below the {facts.present_count} records "
                "present; a source total cannot be fewer than what you see. Use the "
                "SOURCE's claimed total"
                + (f" ({source_total})." if source_total is not None else "."))
        # FORM slip: total wildly above present AND looks like an aggregate.
        if (source_total is not None and claim.total != source_total
                and claim.total > 5 * max(facts.present_count, 1)):
            return Consistency(False,
                f"total={claim.total} doesn't match the source's claimed total "
                f"({source_total}); it looks like a value/sum, not a record count. "
                f"Use {source_total}.")

    if k is CoverageKind.CONTIGUOUS_IDS and claim.total is not None:
        ks = facts.keys
        span = (max(ks) - min(ks) + 1) if ks else 0
        if claim.total not in (span, facts.present_count):
            return Consistency(False,
                f"kind 'contiguous_ids' but total={claim.total} matches neither the "
                f"key-span ({span}) nor the present count ({facts.present_count}).")

    return Consistency(True)


def run_with_repair(declare_fn: DeclareFn, facts: SourceFacts,
                    source_total: int | None, max_repairs: int = 2
                    ) -> tuple[GateResult, list]:
    """Declare -> check-consistency -> (repair)* -> verify.

    Returns (GateResult, trace). The trace is a list of dicts, one per attempt,
    for auditing. Safety is unconditional: the returned GateResult comes from
    verify_coverage, which never false-completes — regardless of how the declarer
    behaves across attempts.
    """
    trace: list[dict] = []
    repair_msg = ""
    claim = CoverageClaim(CoverageKind.NONE)
    for attempt in range(max_repairs + 1):
        claim = declare_fn(facts, source_total, repair_msg)
        cons = check_consistency(claim, facts, source_total)
        trace.append({
            "attempt": attempt,
            "kind": claim.kind.value,
            "total": claim.total,
            "coherent": cons.coherent,
            "diagnostic": cons.diagnostic,
        })
        if cons.coherent:
            break
        repair_msg = cons.diagnostic
    return verify_coverage(claim, facts), trace
