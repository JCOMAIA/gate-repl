"""Predicate-defined completeness — extending the gate beyond enumerable sets.

The set-difference gate works when the requirement is an enumerable set
({200..250}). Many real tasks define the requirement by a PREDICATE: "sum of all
sales > 5000". There is no a-priori set to diff against; membership depends on
data you may not fully have. Completeness becomes a COVERAGE question: "have I
seen every record the predicate could select?"

Coverage is decidable only under an invariant on the SOURCE. The key — and subtle
— finding this experiment surfaces:

  * full_count (len(present) == claimed total)  → STRONG: proves no deletions.
  * sorted_desc + boundary_crossed              → WEAK: proves you've seen all
        AMOUNTS down to the threshold, but NOT that no record was deleted from the
        middle (a deleted record leaves the list sorted and the boundary crossed).
  * contiguous_ids (ids form a full range)      → proves no deletion WITHIN range.

The enumerable-set case got the no-deletion guarantee for free (the required set
WAS the contiguity guarantee). The predicate case forces it to be earned.

Three arms, predicate = "sum of sales with amount > 5000":
  llm_judge    — LLM reads context + metadata, decides complete/incomplete in-head.
  repl_weak    — deterministic: certify COMPLETE on sorted_desc+boundary alone.
  repl_robust  — deterministic: certify COMPLETE only under a deletion-proof
                 invariant (full_count, or sorted+boundary+contiguous_ids).

Prediction:
  llm_judge   false-passes on subtle scenarios (truncation, mid-deletion).
  repl_weak   catches truncation but is FOOLED by mid-deletion (sorted still holds).
  repl_robust catches both — it refuses to certify completeness from sort alone.

Run:
  python -m bench.proto_predicate
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


THRESHOLD = 5000
N = 200


def full_dataset() -> list[tuple[int, int]]:
    """(id, amount) for ids 0..N-1, seeded; amounts straddle the threshold."""
    rng = random.Random(42)
    return [(i, rng.randint(1000, 9000)) for i in range(N)]


DATA = full_dataset()
TRUE_QUALIFYING = [(i, a) for i, a in DATA if a > THRESHOLD]
TRUE_SUM = sum(a for _, a in TRUE_QUALIFYING)


def fmt(records: list[tuple[int, int]]) -> str:
    return "\n".join(f"VENDA_{i}: R$ {a}" for i, a in records)


# --- scenario builders: (records_shown, metadata_line, truly_complete) ---
def scenarios() -> dict[str, tuple[list, str, bool]]:
    s = {}

    # 1. sorted_full: sorted desc, ALL records, boundary crossed -> COMPLETE
    sd = sorted(DATA, key=lambda r: -r[1])
    s["sorted_full"] = (sd, "FONTE: ordenado por valor decrescente; 200 de 200 registros.", True)

    # 2. sorted_truncated: sorted desc, cut ABOVE threshold (boundary NOT crossed) -> INCOMPLETE
    above = [r for r in sd if r[1] >= 6000]
    s["sorted_truncated"] = (above, "FONTE: ordenado por valor decrescente; primeiras linhas (truncado).", False)

    # 3. count_full: unsorted (id order), all records, count metadata -> COMPLETE
    s["count_full"] = (list(DATA), "FONTE: ordem original; 200 de 200 registros (export completo).", True)

    # 4. count_partial: unsorted random 70%, count says 200 but fewer present -> INCOMPLETE
    rng = random.Random(7)
    part = rng.sample(DATA, int(N * 0.7))
    s["count_partial"] = (part, "FONTE: amostra; 140 de 200 registros.", False)

    # 5. sorted_mid_deletion (ADVERSARIAL): sorted desc, boundary crossed, but ONE
    #    qualifying record removed from the middle. Sort STILL holds, boundary STILL
    #    crossed -> weak coverage is fooled; only deletion-proof invariant catches it.
    victim = next(r for r in sd if r[1] > THRESHOLD and 6000 < r[1] < 7000)
    deleted = [r for r in sd if r != victim]
    s["sorted_mid_deletion"] = (deleted,
        "FONTE: ordenado por valor decrescente; export completo.", False)

    return s


SCN_TRUE_SUM: dict[str, int] = {}
for _name, (_recs, _meta, _complete) in scenarios().items():
    SCN_TRUE_SUM[_name] = TRUE_SUM if _complete else sum(a for i, a in _recs if a > THRESHOLD)


# ============================ deterministic verifier ============================

def parse_records(ctx: str) -> list[tuple[int, int]]:
    out = []
    for m in re.finditer(r"VENDA_(\d+):\s*R\$\s*(\d+)", ctx):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def parse_claimed_total(ctx: str) -> int | None:
    # metadata like "200 de 200" or "140 de 200" -> claimed source total is the 2nd
    m = re.search(r"(\d+)\s+de\s+(\d+)", ctx)
    return int(m.group(2)) if m else None


def verify(ctx: str, robust: bool) -> dict:
    recs = parse_records(ctx)
    amounts = [a for _, a in recs]
    ids = [i for i, _ in recs]
    qualifying_sum = sum(a for a in amounts if a > THRESHOLD)
    claimed_total = parse_claimed_total(ctx)

    sorted_desc = all(amounts[k] >= amounts[k + 1] for k in range(len(amounts) - 1))
    boundary_crossed = len(amounts) > 0 and min(amounts) <= THRESHOLD
    full_count = claimed_total is not None and len(recs) == claimed_total
    contiguous = len(ids) > 0 and sorted(ids) == list(range(min(ids), max(ids) + 1))

    if robust:
        # deletion-proof: full_count OR (sorted+boundary AND contiguous ids)
        complete = full_count or (sorted_desc and boundary_crossed and contiguous)
        basis = ("full_count" if full_count else
                 "sorted+boundary+contiguous" if (sorted_desc and boundary_crossed and contiguous)
                 else "none")
    else:
        # weak: sorted+boundary alone (or full_count)
        complete = full_count or (sorted_desc and boundary_crossed)
        basis = ("full_count" if full_count else
                 "sorted+boundary" if (sorted_desc and boundary_crossed) else "none")

    return {
        "complete": complete, "basis": basis,
        "sorted_desc": sorted_desc, "boundary_crossed": boundary_crossed,
        "full_count": full_count, "contiguous": contiguous,
        "result": qualifying_sum if complete else None,
    }


# ============================ LLM judge arm ============================

JUDGE_PROMPT = """Contexto (registros de vendas, pode estar INCOMPLETO):
{ctx}

Tarefa: some o valor de TODAS as vendas com valor acima de R$ 5000.

Voce so pode dar a soma se tiver CERTEZA de que viu TODAS as vendas acima de 5000
que a fonte contem. Avalie a completude considerando a descricao da FONTE.

Responda em uma linha:
- 'COMPLETE: <soma>'  se voce tem certeza de que viu todas as vendas qualificantes.
- 'INCOMPLETE: <motivo>'  se nao pode garantir completude."""

_JUDGE = re.compile(r"\b(COMPLETE|INCOMPLETE)\b", re.IGNORECASE)
_NUM = re.compile(r"COMPLETE:\s*R?\$?\s*([\d.,]+)", re.IGNORECASE)


def llm_judge(client: ORClient, ctx: str) -> dict:
    r = client.chat([{"role": "user", "content": JUDGE_PROMPT.format(ctx=ctx)}])
    txt = r.content
    m = _JUDGE.search(txt)
    decision = m.group(1).upper() if m else "UNKNOWN"
    val = None
    if decision == "COMPLETE":
        nm = _NUM.search(txt)
        if nm:
            val = int(re.sub(r"[.,]", "", nm.group(1)))
    return {"decision": decision, "result": val, "output": txt[:160],
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "elapsed_s": r.elapsed_s,
            "cost_usd": cost_usd(client.model, r.prompt_tokens, r.completion_tokens)}


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"predicate_{run_id}.jsonl")
    scn = scenarios()
    print(f"[predicate] model={cfg.model} predicate='sum sales > {THRESHOLD}' "
          f"true_sum={TRUE_SUM} scenarios={len(scn)}")
    print(f"[predicate] writing -> {out_path}\n")

    tally = {"llm_judge": Counter(), "repl_weak": Counter(), "repl_robust": Counter()}

    with open(out_path, "w", encoding="utf-8") as out:
        for name, (recs, meta, truly_complete) in scn.items():
            ctx = meta + "\n" + fmt(recs)
            true_answer = TRUE_SUM if truly_complete else None  # complete => the full sum
            scn_partial_sum = SCN_TRUE_SUM[name]

            # --- arm 1: LLM judge ---
            j = llm_judge(client, ctx)
            j_correct = grade(j["decision"], j["result"], truly_complete, TRUE_SUM, scn_partial_sum)
            tally["llm_judge"][j_correct] += 1

            # --- arm 2 & 3: deterministic verify ---
            w = verify(ctx, robust=False)
            wv = "COMPLETE" if w["complete"] else "INCOMPLETE"
            w_correct = grade(wv, w["result"], truly_complete, TRUE_SUM, scn_partial_sum)
            tally["repl_weak"][w_correct] += 1

            rb = verify(ctx, robust=True)
            rv = "COMPLETE" if rb["complete"] else "INCOMPLETE"
            r_correct = grade(rv, rb["result"], truly_complete, TRUE_SUM, scn_partial_sum)
            tally["repl_robust"][r_correct] += 1

            row = {
                "scenario": name, "truly_complete": truly_complete,
                "true_sum": TRUE_SUM, "present_qualifying_sum": scn_partial_sum,
                "llm_judge": {"decision": j["decision"], "result": j["result"], "grade": j_correct},
                "repl_weak": {"decision": wv, "basis": w["basis"], "result": w["result"], "grade": w_correct},
                "repl_robust": {"decision": rv, "basis": rb["basis"], "result": rb["result"], "grade": r_correct},
                "invariants": {k: rb[k] for k in ("sorted_desc", "boundary_crossed", "full_count", "contiguous")},
                "model": cfg.model,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            tag = "complete" if truly_complete else "INCOMPLETE"
            print(f"  {name:20} (truly {tag})")
            print(f"     llm_judge   : {j['decision']:10} -> {grade_mark(j_correct)}")
            print(f"     repl_weak   : {wv:10} [{w['basis']:26}] -> {grade_mark(w_correct)}")
            print(f"     repl_robust : {rv:10} [{rb['basis']:26}] -> {grade_mark(r_correct)}")

    n = len(scn)
    print("\n" + "=" * 70)
    print("PREDICATE COMPLETENESS — correct decisions per arm")
    print("=" * 70)
    for arm in ("llm_judge", "repl_weak", "repl_robust"):
        ok = tally[arm]["OK"]
        print(f"  {arm:12}: {ok}/{n} correct   "
              f"(false_complete={tally[arm]['FALSE_COMPLETE']}, "
              f"over_abstain={tally[arm]['OVER_ABSTAIN']}, "
              f"wrong_sum={tally[arm]['WRONG_SUM']})")
    print("\nKey contrast — the mid-deletion scenario:")
    print("  sorted+boundary holds, so repl_weak certifies COMPLETE and computes a")
    print("  wrong sum (a qualifying record was silently deleted). Only repl_robust,")
    print("  which demands a deletion-proof invariant, catches it.")
    print(f"\n[predicate] raw -> {out_path}")


def grade(decision: str, result, truly_complete: bool, true_sum: int, partial_sum: int) -> str:
    """Grade a (decision, result) against truth.
    truly_complete True  -> want COMPLETE with result == true_sum.
    truly_complete False -> want INCOMPLETE (abstain). COMPLETE here is a false-complete."""
    if truly_complete:
        if decision != "COMPLETE":
            return "OVER_ABSTAIN"
        return "OK" if result == true_sum else "WRONG_SUM"
    else:
        return "OK" if decision == "INCOMPLETE" else "FALSE_COMPLETE"


def grade_mark(g: str) -> str:
    return {"OK": "OK", "FALSE_COMPLETE": "XX FALSE-COMPLETE",
            "OVER_ABSTAIN": "~~ over-abstain", "WRONG_SUM": "XX wrong-sum"}.get(g, g)


if __name__ == "__main__":
    main()
