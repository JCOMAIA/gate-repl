"""Enumerable-set completeness: the simplest, most common gate.

When the requirement is an explicit set of keys (IDs 200-250, twelve months, a list
of invoices), completeness is a set difference. This cannot miss an interior
element — unlike eyeballing "the range looks complete", which routinely does.

You provide what the task REQUIRES and what the context CONTAINS, both as sets of
hashable keys. The library decides. Keys can be anything hashable: ints, strings,
dates, tuples.

    from beliefgate import check_set
    res = check_set(required={i for i in range(200, 251)}, present=present_ids)
    if res.ok:
        ... compute the answer ...
    else:
        ... abstain; res.missing has the exact gap ...
"""
from __future__ import annotations

from collections.abc import Iterable, Set
from typing import Hashable

from .types import GateResult, Verdict


def check_set(required: Iterable[Hashable], present: Iterable[Hashable]) -> GateResult:
    """Set-difference completeness.

    required: every key the task needs (the enumerable requirement).
    present:  every key actually found in the context.

    Returns COMPLETE iff required ⊆ present; otherwise INCOMPLETE with the exact
    missing keys. There is no judgment and no model here — pure set difference.
    """
    req: Set = set(required)
    pres: Set = set(present)
    missing = req - pres
    if not missing:
        return GateResult(
            Verdict.COMPLETE,
            reason=f"all {len(req)} required keys present",
            detail={"required": len(req), "present_of_required": len(req)},
        )
    return GateResult(
        Verdict.INCOMPLETE,
        missing=sorted(missing, key=_sortkey),
        reason=f"{len(missing)} of {len(req)} required keys missing",
        detail={"required": len(req), "present_of_required": len(req - missing)},
    )


def _sortkey(x: Hashable):
    """Best-effort stable ordering for the missing list, mixed types tolerated."""
    return (0, x) if isinstance(x, (int, float)) else (1, str(x))
