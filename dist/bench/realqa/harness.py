"""Phase B harness: belief-gate vs baselines on REAL grounded-QA, with an
honest insufficient-context manipulation.

Per example, two conditions:
  complete     — all supporting items present; the question IS answerable.
  insufficient — one supporting item removed; the question is NOT answerable from
                 context, so the honest answer is "I don't have enough".

Four methods decide SUFFICIENT / INSUFFICIENT:
  rag_naive   — answer directly; we treat a committed answer as "claimed sufficient".
  llm_judge   — "Sufficient Context" autorater: classify SUFFICIENT/INSUFFICIENT.
  llm_cot     — same, think step by step first.
  belief_gate — LLM lists which [ITEM k] ids it sees; set difference vs the known
                supporting set decides. (The required set = the example's supporting
                ids; present = ids the model reports seeing.)

Primary metric: FALSE-SUFFICIENT on the insufficient condition (claiming you can
answer when a supporting item is gone — the dangerous error). Secondary:
over-abstention on the complete condition, plus tokens/latency.

Usage:
  python -m bench.realqa.harness --dataset drop  --path data/drop_dev.json --n 40
  python -m bench.realqa.harness --dataset finqa --path data/finqa_dev.json --n 40
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
from .adapters import ADAPTERS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "beliefgate"))
from beliefgate import check_set, Verdict   # noqa: E402


JUDGE_P = """Contexto (trechos rotulados [ITEM k]):
{ctx}

Pergunta: {q}

A pergunta SÓ pode ser respondida se o contexto contiver TODA a evidência
necessária. Avalie. Responda exatamente:
'SUFFICIENT' — se há evidência suficiente para responder, ou
'INSUFFICIENT' — se falta evidência necessária."""

COT_P = """Contexto (trechos rotulados [ITEM k]):
{ctx}

Pergunta: {q}

Pense passo a passo: identifique qual evidência a pergunta exige, depois verifique
se ela está presente no contexto. Então responda 'SUFFICIENT' ou 'INSUFFICIENT'."""

NAIVE_P = """Contexto (trechos rotulados [ITEM k]):
{ctx}

Pergunta: {q}

Responda à pergunta com base APENAS no contexto. Se não houver evidência suficiente,
responda exatamente 'INSUFFICIENT'. Caso contrário responda 'ANSWER: <resposta>'."""

RELEVANCE_P = """Contexto (cada trecho começa com uma tag [ITEM k]):
{ctx}

Pergunta: {q}

Identifique QUAIS itens de evidência seriam NECESSÁRIOS para responder esta
pergunta — pense na evidência que a resposta exige, não no que está presente.
Liste os ids desses itens como lista Python. Ex: REQUIRED: ['table_3', 'text_5'].
Liste apenas os ids; não responda a pergunta."""

_SUFF = re.compile(r"\b(INSUFFICIENT|SUFFICIENT)\b", re.IGNORECASE)
_REQUIRED = re.compile(r"REQUIRED:\s*\[([^\]]*)\]", re.IGNORECASE)
_TOKEN = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def _decide_llm(client, template, ctx, q):
    r = client.chat([{"role": "user", "content": template.format(ctx=ctx, q=q)}])
    m = _SUFF.search(r.content)
    dec = m.group(1).upper() if m else None
    return dec, r.content[:160], r.prompt_tokens, r.completion_tokens, r.elapsed_s


def _decide_naive(client, ctx, q):
    r = client.chat([{"role": "user", "content": NAIVE_P.format(ctx=ctx, q=q)}])
    txt = r.content
    if re.search(r"\bINSUFFICIENT\b", txt, re.IGNORECASE) and "ANSWER:" not in txt.upper():
        dec = "INSUFFICIENT"
    else:
        dec = "SUFFICIENT"   # committed an answer
    return dec, txt[:160], r.prompt_tokens, r.completion_tokens, r.elapsed_s


def _present_in_ctx(ctx: str, ids: set) -> set:
    """DETERMINISTIC presence: an id is present iff its [ITEM <id>] tag is in ctx.
    The context is rendered by us, so this is exact — no judgment, no halluc."""
    return {str(i) for i in ids if f"[ITEM {i}]" in ctx}


def _decide_hybrid(client, ctx, q):
    """The fair, real architecture: the LLM does ONLY the semantic part — declaring
    which items it judges NECESSARY (the required set). The gate then verifies
    presence deterministically (set difference). Same information as llm_judge
    (context + question, NO gold oracle); the only difference is decomposition:
    judge fuses 'what do I need?' + 'is it here?'; hybrid separates them."""
    r = client.chat([{"role": "user", "content": RELEVANCE_P.format(ctx=ctx, q=q)}])
    m = _REQUIRED.search(r.content)
    required = set()
    if m:
        for a, b in _TOKEN.findall(m.group(1)):
            tok = (a or b).strip()
            if tok:
                required.add(tok)
    if not required:
        # LLM named no required items -> can't verify -> abstain (safe side)
        return "INSUFFICIENT", "no required items declared", r.prompt_tokens, r.completion_tokens, r.elapsed_s
    present = _present_in_ctx(ctx, required)
    res = check_set(required=required, present=present)
    dec = "SUFFICIENT" if res.verdict is Verdict.COMPLETE else "INSUFFICIENT"
    return dec, f"req={sorted(required)} {res}", r.prompt_tokens, r.completion_tokens, r.elapsed_s


def grade(decision, truly_sufficient):
    if decision is None:
        return "UNKNOWN"
    if truly_sufficient:
        return "OK" if decision == "SUFFICIENT" else "OVER_ABSTAIN"
    return "OK" if decision == "INSUFFICIENT" else "FALSE_SUFFICIENT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(ADAPTERS))
    ap.add_argument("--path", required=True, help="path to the dataset json")
    ap.add_argument("--n", type=int, default=40, help="number of examples")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)

    examples = ADAPTERS[args.dataset](args.path, limit=args.n * 3)
    if not examples:
        raise SystemExit(f"No usable examples from {args.path}")
    rng = random.Random(args.seed)
    rng.shuffle(examples)
    examples = examples[: args.n]

    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"realqa_{args.dataset}_{run_id}.jsonl")
    print(f"[realqa] dataset={args.dataset} model={cfg.model} n={len(examples)}")
    print(f"[realqa] writing -> {out_path}\n")

    methods = ["rag_naive", "llm_judge", "llm_cot", "hybrid"]
    tally = {m: {"complete": Counter(), "insufficient": Counter()} for m in methods}
    cost = Counter()

    with open(out_path, "w", encoding="utf-8") as out:
        for ei, ex in enumerate(examples):
            support = list(ex.supporting)
            drop_id = rng.choice(support)
            conds = {
                "complete": (ex.context_text(), True),
                "insufficient": (ex.context_text(drop={drop_id}), False),
            }
            for cond, (ctx, truly) in conds.items():
                for method in methods:
                    if method == "rag_naive":
                        dec, raw, pt, ct, el = _decide_naive(client, ctx, ex.question)
                    elif method == "llm_judge":
                        dec, raw, pt, ct, el = _decide_llm(client, JUDGE_P, ctx, ex.question)
                    elif method == "llm_cot":
                        dec, raw, pt, ct, el = _decide_llm(client, COT_P, ctx, ex.question)
                    else:  # hybrid: LLM declares required, gate verifies present
                        dec, raw, pt, ct, el = _decide_hybrid(client, ctx, ex.question)
                    g = grade(dec, truly)
                    tally[method][cond][g] += 1
                    cost[method] += ct
                    out.write(json.dumps({
                        "i": ei, "qid": ex.qid, "dataset": args.dataset, "condition": cond,
                        "method": method, "truly_sufficient": truly, "dropped": str(drop_id),
                        "decision": dec, "grade": g, "answer_type": ex.answer_type,
                        "n_support": len(support), "raw": raw,
                        "completion_tokens": ct, "elapsed_s": el,
                        "cost_usd": cost_usd(cfg.model, pt, ct), "model": cfg.model,
                    }, ensure_ascii=False) + "\n")
                    out.flush()
            print(f"  {ei+1}/{len(examples)} done")

    n = len(examples)
    print("\n" + "=" * 80)
    print(f"REAL-QA [{args.dataset}] — belief-gate vs baselines (n={n})")
    print("=" * 80)
    print(f"{'method':12}{'FALSE-SUFF':>14}{'over-abstain':>16}{'unknown':>10}{'~tokens':>12}")
    print(f"{'':12}{'(insufficient)':>14}{'(complete)':>16}")
    for m in methods:
        fs = tally[m]["insufficient"]["FALSE_SUFFICIENT"]
        oa = tally[m]["complete"]["OVER_ABSTAIN"]
        unk = tally[m]["complete"]["UNKNOWN"] + tally[m]["insufficient"]["UNKNOWN"]
        print(f"{m:12}{fs:>9}/{n:<4}{oa:>11}/{n:<4}{unk:>10}{cost[m]:>12}")
    print("\nFALSE-SUFFICIENT = claimed answerable when a supporting item was removed")
    print("(the dangerous error). over-abstain = declared insufficient when complete.")
    print(f"\n[realqa] raw -> {out_path}")


if __name__ == "__main__":
    main()
