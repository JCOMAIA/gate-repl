"""Core types for belief-gate.

A gate decision is one of three verdicts. The whole library exists to guarantee
one property: a gate NEVER returns COMPLETE for context that isn't actually
complete. It may over-refuse (INCOMPLETE/UNDECIDABLE when it could have answered),
but it never false-completes. Refusing a valid task is tolerable; certifying an
invalid one is catastrophic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    COMPLETE = "COMPLETE"        # coverage proven; an answer may be computed
    INCOMPLETE = "INCOMPLETE"    # a gap is proven; the exact missing items are known
    UNDECIDABLE = "UNDECIDABLE"  # cannot decide from what's available (e.g. an
                                 # external field is needed) — distinct from a gap


@dataclass(frozen=True)
class GateResult:
    verdict: Verdict
    missing: list = field(default_factory=list)   # for INCOMPLETE: exact missing keys
    reason: str = ""                              # human-readable basis
    detail: dict = field(default_factory=dict)    # machine-usable extras

    @property
    def ok(self) -> bool:
        """True only when coverage is proven."""
        return self.verdict is Verdict.COMPLETE

    def __str__(self) -> str:
        if self.verdict is Verdict.INCOMPLETE and self.missing:
            return f"{self.verdict.value}: missing {self.missing} ({self.reason})"
        return f"{self.verdict.value}: {self.reason}"
