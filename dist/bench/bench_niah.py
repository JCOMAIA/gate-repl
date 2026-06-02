"""Multi-needle-in-haystack: belief-gate vs three real baselines, on real text.

The honest framing — belief-gate is NOT general QA. It verifies that an ENUMERABLE
requirement is fully present. So we use the task where that is exactly the question:
"were ALL N needles retrieved?" The required set is {needle_1..needle_N}; the
context is what a retriever returned; sometimes a needle is missing (adversarial).
A system must decide SUFFICIENT (all needles present) or INSUFFICIENT (one missing)
and, if it claims sufficient, report them.

Haystack is REAL dense text (academic papers in the repo), not lorem ipsum.

Four methods decide sufficiency:
  rag_naive    — stuff context, ask for all needles, answer (no gate). Baseline.
  llm_judge    — "Sufficient Context" autorater style: an LLM classifies
                 SUFFICIENT / INSUFFICIENT (the published competitor).
  llm_cot      — same, but "think step by step" first (self-critique CoT).
  belief_gate  — deterministic: the LLM is asked ONLY to list which needle IDs it
                 sees; the library computes required - present (set difference).

Primary metric: FALSE-SUFFICIENT rate — declaring "all present" when one is
missing. That is the dangerous error (a confident wrong "complete"). Secondary:
over-abstention (declaring missing when all are present).

Run:
  python -m bench.bench_niah
"""
import json
import os
import random
import re
import time
from collections import Counter

from . import config
from .client import ORClient
from .pricing import cost_usd

# belief-gate library (the deterministic core under test)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "beliefgate"))
from beliefgate import check_set, Verdict   # noqa: E402


HAYSTACK_FILES = ["rlm.txt", "COT.txt", "LIFEHARNESS.txt", "MemCollab.txt"]
N_NEEDLES = 8          # required set size
TRIALS = 10            # per (method, condition)
TOL_FILLER_LINES = 0


def load_haystack() -> list[str]:
    lines = []
    for fn in HAYSTACK_FILES:
        p = os.path.join(os.path.dirname(__file__), "..", fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="ignore") as f:
                lines += [ln.strip() for ln in f if len(ln.strip()) > 40]
    return lines


HAY = load_haystack()


def make_needle(i: int) -> str:
    # a distinctive, unambiguous needle line with a stable ID
    return f"FACT_{i:03d}: o código de verificação da seção {i} é XK{i:04d}Z."


def build_case(rng: random.Random, drop_one: bool):
    """Insert N needles into a real-text haystack at random positions, in shuffled
    ID order. If drop_one, omit exactly one needle from the RETRIEVED context (but
    it is still 'required'). Returns (context_text, required_ids, missing_id|None)."""
    ids = list(range(1, N_NEEDLES + 1))
    present_ids = list(ids)
    missing = None
    if drop_one:
        missing = rng.choice(ids)
        present_ids = [i for i in ids if i != missing]

    # sample real lines as filler, insert needles at random positions, shuffle order
    filler = rng.sample(HAY, min(120, len(HAY)))
    needle_lines = [make_needle(i) for i in present_ids]
    rng.shuffle(needle_lines)
    body = filler[:]
    for nl in needle_lines:
        body.insert(rng.randint(0, len(body)), nl)
    return "\n".join(body), ids, missing


# ----------------------------- methods -----------------------------

TASK = (f"O contexto deveria conter {N_NEEDLES} linhas FACT_001..FACT_{N_NEEDLES:03d}, "
        f"cada uma com um código de verificação.")

NAIVE_P = """Contexto:
{ctx}

{task}
Liste os códigos de TODAS as {n} linhas FACT. Se tiver todos, responda
'SUFFICIENT: <lista>'. Responda apenas isso."""

JUDGE_P = """Contexto:
{ctx}

{task}
Avalie se o contexto contém TODAS as {n} linhas FACT necessárias (FACT_001 a
FACT_{n:03d}). Responda exatamente 'SUFFICIENT' ou 'INSUFFICIENT: <o que falta>'."""

COT_P = """Contexto:
{ctx}

{task}
Pense passo a passo: verifique cada FACT de 001 a {n:03d}, uma por uma. Depois
responda 'SUFFICIENT' se todas estão presentes, ou 'INSUFFICIENT: <faltantes>'."""

GATE_P = """Contexto:
{ctx}

Liste APENAS os IDs das linhas FACT presentes no contexto, como uma lista Python de
inteiros. Exemplo: PRESENT: [1, 3, 4]. Não julgue completude; só liste o que vê."""

_SUFF = re.compile(r"\b(INSUFFICIENT|SUFFICIENT)\b", re.IGNORECASE)
_PRESENT = re.compile(r"PRESENT:\s*\[([^\]]*)\]", re.IGNORECASE)
_IDS = re.compile(r"FACT_0*(\d+)|XK0*(\d+)Z|\b(\d{1,3})\b")


def decide_llm(client, ctx, template):
    r = client.chat([{"role": "user", "content": template.format(ctx=ctx, task=TASK, n=N_NEEDLES)}])
    m = _SUFF.search(r.content)
    decision = m.group(1).upper() if m else "UNKNOWN"
    return decision, r.content[:120], r.prompt_tokens, r.completion_tokens, r.elapsed_s


def decide_gate(client, ctx, required_ids):
    r = client.chat([{"role": "user", "content": GATE_P.format(ctx=ctx)}])
    m = _PRESENT.search(r.content)
    present = set()
    if m:
        present = {int(x) for x in re.findall(r"\d+", m.group(1))}
    res = check_set(required=required_ids, present=present)
    decision = "SUFFICIENT" if res.verdict is Verdict.COMPLETE else "INSUFFICIENT"
    return decision, res, r.prompt_tokens, r.completion_tokens, r.elapsed_s


def grade(decision, truly_sufficient):
    if truly_sufficient:
        return "OK" if decision == "SUFFICIENT" else "OVER_ABSTAIN"
    return "OK" if decision == "INSUFFICIENT" else "FALSE_SUFFICIENT"


def main():
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"niah_{run_id}.jsonl")
    if not HAY:
        raise SystemExit("No haystack text found (need rlm.txt etc. in repo root).")
    print(f"[niah] model={cfg.model} needles={N_NEEDLES} trials={TRIALS} "
          f"haystack_lines={len(HAY)}")
    print(f"[niah] writing -> {out_path}\n")

    methods = ["rag_naive", "llm_judge", "llm_cot", "belief_gate"]
    # tally[method][condition] = Counter of grades
    tally = {m: {"complete": Counter(), "missing": Counter()} for m in methods}
    cost = Counter()
    rng = random.Random(2026)

    with open(out_path, "w", encoding="utf-8") as out:
        for trial in range(TRIALS):
            for cond, drop in [("complete", False), ("missing", True)]:
                ctx, required, missing = build_case(rng, drop)
                truly_suff = (missing is None)
                for method in methods:
                    if method == "rag_naive":
                        dec, raw, pt, ct, el = decide_llm(client, ctx, NAIVE_P)
                        # naive: treat any "SUFFICIENT" or a full list as sufficient
                        dec = "SUFFICIENT" if "SUFFICIENT" in raw.upper() else "INSUFFICIENT"
                    elif method == "llm_judge":
                        dec, raw, pt, ct, el = decide_llm(client, ctx, JUDGE_P)
                    elif method == "llm_cot":
                        dec, raw, pt, ct, el = decide_llm(client, ctx, COT_P)
                    else:
                        dec, res, pt, ct, el = decide_gate(client, ctx, required)
                        raw = str(res)
                    g = grade(dec, truly_suff)
                    tally[method][cond][g] += 1
                    cost[method] += ct
                    out.write(json.dumps({
                        "trial": trial, "condition": cond, "method": method,
                        "truly_sufficient": truly_suff, "missing_id": missing,
                        "decision": dec, "grade": g, "raw": raw[:140],
                        "completion_tokens": ct, "elapsed_s": el,
                        "cost_usd": cost_usd(cfg.model, pt, ct), "model": cfg.model,
                    }, ensure_ascii=False) + "\n")
                    out.flush()
            print(f"  trial {trial+1}/{TRIALS} done")

    print("\n" + "=" * 78)
    print("MULTI-NEEDLE: belief-gate vs baselines (real haystack)")
    print("=" * 78)
    print(f"{'method':12}{'FALSE-SUFF':>14}{'over-abstain':>16}{'~tokens':>12}")
    print(f"{'':12}{'(missing cond)':>14}{'(complete cond)':>16}")
    for m in methods:
        fs = tally[m]["missing"]["FALSE_SUFFICIENT"]
        oa = tally[m]["complete"]["OVER_ABSTAIN"]
        print(f"{m:12}{fs:>9}/{TRIALS:<4}{oa:>11}/{TRIALS:<4}{cost[m]:>12}")
    print("\nFALSE-SUFFICIENT = declared 'all present' when one needle was missing")
    print("(the dangerous error). over-abstain = declared missing when all present.")
    print(f"\n[niah] raw -> {out_path}")


if __name__ == "__main__":
    main()
