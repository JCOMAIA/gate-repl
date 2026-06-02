"""Dataset adapters: raw file -> list[QAExample]. Format-specific, isolated here.

Each adapter yields QAExamples with an enumerable `supporting` set so the harness
can drop a supporting item to create the INSUFFICIENT condition.

Supported (point at the official released files):
  - DROP   (drop_dataset_train.json / dev): paragraph + QA pairs. We split the
    paragraph into sentences as items; supporting = sentences containing the
    answer's evidence numbers/spans (heuristic, documented below).
  - FinQA  (train.json / dev.json): table + pre/post text + a program. Items are
    table rows + text sentences; supporting = the rows/sentences referenced by the
    gold program's arguments.

If a dataset ships gold supporting-fact annotations, prefer those over heuristics.
"""
from __future__ import annotations

import json
import re

from .schema import QAExample, QAItem


# ----------------------------- DROP -----------------------------

def _sentences(text: str) -> list[str]:
    # light sentence split; good enough to make enumerable items
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if len(p.strip()) > 3]


def load_drop(path: str, limit: int | None = None, only_numeric: bool = True):
    """DROP official json: {passage_id: {"passage": str, "qa_pairs": [...]}}.

    supporting heuristic: sentences that contain any token of the gold answer
    (number or span). For numeric answers this reliably captures the evidence
    sentence(s); we keep only examples where >=1 supporting sentence is found.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: list[QAExample] = []
    for pid, blob in data.items():
        passage = blob["passage"]
        sents = _sentences(passage)
        items = [QAItem(id=i, text=s) for i, s in enumerate(sents)]
        for qa in blob.get("qa_pairs", []):
            ans, atype = _drop_answer(qa.get("answer", {}))
            if ans is None:
                continue
            if only_numeric and atype != "number":
                continue
            support = _drop_support(sents, ans, qa.get("question", ""))
            if not support:
                continue
            out.append(QAExample(
                qid=qa.get("query_id", f"{pid}"),
                question=qa["question"],
                answer=ans,
                items=items,
                supporting=support,
                answer_type=atype,
                meta={"passage_id": pid},
            ))
            if limit and len(out) >= limit:
                return out
    return out


def _drop_answer(a: dict) -> tuple[str | None, str]:
    if a.get("number", "") != "":
        return str(a["number"]), "number"
    if a.get("spans"):
        return " ".join(a["spans"]), "span"
    d = a.get("date") or {}
    if any(d.values()):
        return " ".join(str(d.get(k, "")) for k in ("day", "month", "year")).strip(), "date"
    return None, "none"


def _drop_support(sents: list[str], answer: str, question: str = "") -> list[int]:
    """Heuristic supporting set for DROP.

    DROP numeric answers are usually DERIVED (sum/diff/count), so the answer string
    often does NOT appear literally in the passage. We therefore mark as supporting
    any sentence that (a) contains the literal answer, OR (b) contains a number AND
    shares a content word with the question. This over-includes a little, which is
    SAFE for our purpose: dropping any true supporting sentence still removes
    evidence; the gate's required set is exactly this annotated set, so it is
    internally consistent. Examples with no number-bearing sentence are skipped.
    """
    ans_toks = [t.lower() for t in re.findall(r"\w+", answer) if len(t) > 1]
    q_words = {t.lower() for t in re.findall(r"[A-Za-z]{4,}", question)}
    sup = []
    for i, s in enumerate(sents):
        low = s.lower()
        has_num = bool(re.search(r"\d", s))
        literal = any(t in low for t in ans_toks)
        q_overlap = has_num and bool(q_words & set(re.findall(r"[a-z]{4,}", low)))
        if literal or q_overlap:
            sup.append(i)
    return sup


# ----------------------------- FinQA -----------------------------

def load_finqa(path: str, limit: int | None = None):
    """FinQA official json: list of {id, qa:{question, answer, program,
    gold_inds}, table, pre_text, post_text}. Items = table rows + text sentences;
    supporting = the indices referenced in gold_inds (the dataset's own evidence
    annotation). This is the clean case: real gold supporting facts."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: list[QAExample] = []
    for ex in data:
        qa = ex.get("qa", {})
        ans = str(qa.get("answer", "")).strip()
        if not ans:
            continue
        items, idmap = [], {}
        # table rows
        for ri, row in enumerate(ex.get("table", [])):
            rid = f"table_{ri}"
            items.append(QAItem(id=rid, text=" | ".join(str(c) for c in row)))
            idmap[f"table_{ri}"] = rid
        # text sentences
        for ti, s in enumerate(ex.get("pre_text", []) + ex.get("post_text", [])):
            sid = f"text_{ti}"
            items.append(QAItem(id=sid, text=str(s)))
            idmap[f"text_{ti}"] = sid
        # gold_inds maps like {"table_3": "...", "text_5": "..."}
        support = [idmap[k] for k in qa.get("gold_inds", {}) if k in idmap]
        if not support:
            continue
        out.append(QAExample(
            qid=str(ex.get("id", "")),
            question=qa.get("question", ""),
            answer=ans,
            items=items,
            supporting=support,
            answer_type="number",
            meta={"program": qa.get("program", "")},
        ))
        if limit and len(out) >= limit:
            return out
    return out


ADAPTERS = {"drop": load_drop, "finqa": load_finqa}
