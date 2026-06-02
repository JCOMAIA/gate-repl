"""belief-gate — verify context completeness by execution, not by judgment.

A small, dependency-free, domain-agnostic library that decides whether a context
actually contains everything a task requires — and refuses (with the exact gap)
rather than answering over incomplete data. The core guarantee, enforced by tests:
the gate NEVER returns COMPLETE for context that isn't complete. It errs only
toward refusal.

Two levels:

1. Enumerable set (the common case):
       from beliefgate import check_set
       res = check_set(required={...}, present={...})
       if res.ok: compute() else: abstain(res.missing)

2. Predicate coverage (the advanced case — "all sales > 5000"):
       from beliefgate import CoverageClaim, CoverageKind, SourceFacts, verify_coverage
       facts = SourceFacts(present_count=..., keys=[...], sorted_desc=...,
                           boundary_crossed=..., predicate_evaluable=...)
       res = verify_coverage(CoverageClaim(CoverageKind.FULL_COUNT, total=200), facts)

   With an LLM declaring the claim, wrap it in the repair loop:
       from beliefgate import run_with_repair
       res, trace = run_with_repair(my_declare_fn, facts, source_total=200)

The LLM is always YOURS — the library is the deterministic part that carries the
safety guarantee. See README for a domain-adaptation guide.
"""
from .types import Verdict, GateResult
from .setgate import check_set
from .coverage import (CoverageKind, CoverageClaim, SourceFacts, DELETION_PROOF,
                       verify_coverage)
from .repair import Consistency, check_consistency, run_with_repair, DeclareFn

__version__ = "0.1.0"

__all__ = [
    "Verdict", "GateResult",
    "check_set",
    "CoverageKind", "CoverageClaim", "SourceFacts", "DELETION_PROOF", "verify_coverage",
    "Consistency", "check_consistency", "run_with_repair", "DeclareFn",
]
