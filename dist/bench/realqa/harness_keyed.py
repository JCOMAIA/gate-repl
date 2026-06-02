"""Phase B (correct regime): aggregation over a REAL table where the required keys
come from the QUESTION, not from annotation — so belief-gate legitimately applies.

We reuse real FinQA tables (authentic financial data) but pose a task whose
required set is question-derived and SURVIVES the absence of data:

    "Sum the values in columns <C1>, <C2>, <C3> of the table."

The required keys are the named column headers {C1, C2, C3} — declarable from the
question even if a column is removed. The INSUFFICIENT condition drops one named
column from the table. A correct system must notice that a REQUESTED column is
gone. This is the regime the lib is for: enumerable, task-derived required set.

Methods decide SUFFICIENT / INSUFFICIENT:
  rag_naive   — try to compute the sum; committing = claiming sufficient.
  llm_judge   — classify sufficiency.
  llm_cot     — classify after step-by-step.
  belief_gate — required = the question's named columns; present = columns whose
                header literally appears in the table; set difference decides.
                The key "2020" is declarable even when the 2020 column is removed,
                because the QUESTION names it — that is the whole point.

Usage:
  python -m bench.realqa.harness_keyed --path data/dev.json --n 40
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter

from .. import config
from ..client import ORClient
from ..pricing import cost_usd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "beliefgate"))
from beliefgate import check_set, Verdict   # noqa: E402


def load_tables(path: str, min_cols=4, min_rows=3, limit=400):
    """Pull real tables from FinQA json that have enough named numeric columns."""
    data = json.load(open(path, encoding="utf-8"))
    tables = []
    for ex in data:
        t = ex.get("table", [])
        if len(t) < min_rows + 1:
            continue
        header = [str(c).strip() for c in t[0]]
        # columns 1..k are data columns; col 0 is the row label
        named = [(j, header[j]) for j in range(1, len(header))
                 if header[j] and not header[j].isdigit() or _looks_year(header[j])]
        # keep columns with a usable header and numeric body
        good = []
        for j, name in named:
            col_vals = [_num(t[r][j]) for r in range(1, len(t)) if j < len(t[r])]
            if name and sum(v is not None for v in col_vals) >= min_rows:
                good.append((j, name))
        if len(good) >= 3:
            tables.append({"id": ex.get("id", ""), "table": t, "cols": good})
        if len(tables) >= limit:
            break
    return tables


def _looks_year(s: str) -> bool:
    return bool(re.fullmatch(r"(19|20)\d{2}", s.strip()))


def _num(x):
    s = str(x).replace(",", "").replace("$", "").replace("%", "").replace("(", "-").replace(")", "")
    try:
        return float(s)
    except ValueError:
        return None


def render_table(table, drop_col: int | None = None) -> str:
    lines = []
    for row in table:
        cells = [str(c) for jc, c in enumerate(row) if jc != drop_col]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def build_case(rng, tbl):
    """Pick 3 named columns as the required set; render table, optionally drop one."""
    cols = rng.sample(tbl["cols"], 3)        # [(j, name), ...]
    required = {name for _, name in cols}
    # ground-truth sums per column (for an answerable check, not strictly needed)
    return cols, required


# ----------------------------- methods -----------------------------

def _task(required_names):
    cols = ", ".join(sorted(required_names))
    return f"Some todos os valores numéricos das colunas: {cols}."

NAIVE_P = """Tabela:
{ctx}

{task}
Se alguma coluna pedida não existir na tabela, responda exatamente 'INSUFFICIENT'.
Caso contrário responda 'ANSWER: <soma total>'."""

JUDGE_P = """Tabela:
{ctx}

{task}
A tarefa só pode ser cumprida se TODAS as colunas pedidas existirem na tabela.
Responda exatamente 'SUFFICIENT' ou 'INSUFFICIENT'."""

COT_P = """Tabela:
{ctx}

{task}
Verifique, uma a uma, se cada coluna pedida está presente na tabela. Depois responda
'SUFFICIENT' ou 'INSUFFICIENT'."""

GATE_P = """Tabela:
{ctx}

Liste APENAS os nomes das colunas (cabeçalhos) que aparecem na primeira linha da
tabela, como lista Python. Ex: COLUMNS: ['2019', '2020']. Não some nada."""

_SUFF = re.compile(r"\b(INSUFFICIENT|SUFFICIENT)\b", re.IGNORECASE)
_COLS = re.compile(r"COLUMNS:\s*\[([^\]]*)\]", re.IGNORECASE)
_TOK = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def _decide_llm(client, template, ctx, task):
    r = client.chat([{"role": "user", "content": template.format(ctx=ctx, task=task)}])
    m = _SUFF.search(r.content)
    return (m.group(1).upper() if m else None), r.content[:140], r.prompt_tokens, r.completion_tokens, r.elapsed_s


def _decide_naive(client, ctx, task):
    r = client.chat([{"role": "user", "content": NAIVE_P.format(ctx=ctx, task=task)}])
    txt = r.content
    dec = "INSUFFICIENT" if (re.search(r"\bINSUFFICIENT\b", txt, re.I) and "ANSWER:" not in txt.upper()) else "SUFFICIENT"
    return dec, txt[:140], r.prompt_tokens, r.completion_tokens, r.elapsed_s


def _decide_gate(client, ctx, required: set):
    """required = the QUESTION's named columns (survives a dropped column).
    present = columns the LLM reports seeing in the header. set difference decides.
    The LLM only EXTRACTS visible headers (an easy, verifiable task); it does not
    judge sufficiency. The required set is fixed by the question, so a dropped
    column is caught even though the model can't see it."""
    r = client.chat([{"role": "user", "content": GATE_P.format(ctx=ctx)}])
    m = _COLS.search(r.content)
    present = set()
    if m:
        for a, b in _TOK.findall(m.group(1)):
            tok = (a or b).strip()
            if tok:
                present.add(tok)
    res = check_set(required=required, present=present & required if present else set())
    dec = "SUFFICIENT" if res.verdict is Verdict.COMPLETE else "INSUFFICIENT"
    return dec, f"req={sorted(required)} present={sorted(present)} -> {res.verdict.value}", \
        r.prompt_tokens, r.completion_tokens, r.elapsed_s


def grade(decision, truly_sufficient):
    if decision is None:
        return "UNKNOWN"
    if truly_sufficient:
        return "OK" if decision == "SUFFICIENT" else "OVER_ABSTAIN"
    return "OK" if decision == "INSUFFICIENT" else "FALSE_SUFFICIENT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    tables = load_tables(args.path)
    if len(tables) < args.n:
        print(f"[warn] only {len(tables)} usable tables")
    rng = random.Random(args.seed)
    rng.shuffle(tables)
    tables = tables[: args.n]

    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"keyed_{run_id}.jsonl")
    print(f"[keyed] model={cfg.model} tables={len(tables)} (real FinQA tables, task-derived keys)")
    print(f"[keyed] writing -> {out_path}\n")

    methods = ["rag_naive", "llm_judge", "llm_cot", "belief_gate"]
    tally = {m: {"complete": Counter(), "insufficient": Counter()} for m in methods}
    cost = Counter()

    with open(out_path, "w", encoding="utf-8") as out:
        for ti, tbl in enumerate(tables):
            cols, required = build_case(rng, tbl)
            task = _task(required)
            drop_j, drop_name = rng.choice(cols)
            conds = {
                "complete": (render_table(tbl["table"]), True),
                "insufficient": (render_table(tbl["table"], drop_col=drop_j), False),
            }
            for cond, (ctx, truly) in conds.items():
                for method in methods:
                    if method == "rag_naive":
                        dec, raw, pt, ct, el = _decide_naive(client, ctx, task)
                    elif method == "llm_judge":
                        dec, raw, pt, ct, el = _decide_llm(client, JUDGE_P, ctx, task)
                    elif method == "llm_cot":
                        dec, raw, pt, ct, el = _decide_llm(client, COT_P, ctx, task)
                    else:
                        dec, raw, pt, ct, el = _decide_gate(client, ctx, required)
                    g = grade(dec, truly)
                    tally[method][cond][g] += 1
                    cost[method] += ct
                    out.write(json.dumps({
                        "i": ti, "tid": tbl["id"], "condition": cond, "method": method,
                        "truly_sufficient": truly, "dropped_col": drop_name,
                        "required": sorted(required), "decision": dec, "grade": g,
                        "raw": raw, "completion_tokens": ct, "elapsed_s": el,
                        "cost_usd": cost_usd(cfg.model, pt, ct), "model": cfg.model,
                    }, ensure_ascii=False) + "\n")
                    out.flush()
            print(f"  {ti+1}/{len(tables)} done")

    n = len(tables)
    print("\n" + "=" * 80)
    print(f"KEYED AGGREGATION (real tables, task-derived required) — n={n}")
    print("=" * 80)
    print(f"{'method':12}{'FALSE-SUFF':>14}{'over-abstain':>16}{'~tokens':>12}")
    print(f"{'':12}{'(insufficient)':>14}{'(complete)':>16}")
    for m in methods:
        fs = tally[m]["insufficient"]["FALSE_SUFFICIENT"]
        oa = tally[m]["complete"]["OVER_ABSTAIN"]
        print(f"{m:12}{fs:>9}/{n:<4}{oa:>11}/{n:<4}{cost[m]:>12}")
    print("\nFALSE-SUFFICIENT = claimed all columns present when a requested column")
    print("was removed (the dangerous error). over-abstain = false alarm on complete.")
    print(f"\n[keyed] raw -> {out_path}")


if __name__ == "__main__":
    main()
