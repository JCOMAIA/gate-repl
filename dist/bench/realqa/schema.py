"""Format-agnostic schema for real grounded-QA datasets (DROP, FinQA, TAT-QA...).

A dataset adapter turns each raw example into a `QAExample`. The harness then
manipulates completeness and runs the methods — it never touches dataset format.

The key field is `supporting`: the set of evidence ITEM IDS the answer depends on
(span ids, table-cell ids, fact ids — whatever the dataset annotates). This is the
enumerable `required` set the gate checks. When we drop one supporting item from
the context, the question becomes unanswerable, and the honest answer flips to
INSUFFICIENT — which is exactly what we measure each method's ability to detect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable


@dataclass
class QAItem:
    """One retrievable piece of evidence (a paragraph span, a table row/cell, a
    fact line). `id` is stable; `text` is what goes into the context."""
    id: Hashable
    text: str


@dataclass
class QAExample:
    qid: str
    question: str
    answer: str                       # gold answer (string, normalized by grader)
    items: list[QAItem]               # ALL evidence items available
    supporting: list[Hashable]        # ids of items the answer truly depends on
    answer_type: str = "span"         # "number" | "span" | "count" | "date" ...
    meta: dict = field(default_factory=dict)

    def context_text(self, drop: set[Hashable] | None = None) -> str:
        """Render the context, optionally omitting some item ids (the insufficient
        manipulation). Items keep stable ID tags so a gate can enumerate them."""
        drop = drop or set()
        lines = []
        for it in self.items:
            if it.id in drop:
                continue
            lines.append(f"[ITEM {it.id}] {it.text}")
        return "\n".join(lines)

    def present_ids(self, drop: set[Hashable] | None = None) -> set[Hashable]:
        drop = drop or set()
        return {it.id for it in self.items if it.id not in drop}
