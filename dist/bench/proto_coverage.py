"""Declared coverage invariant — moving "which proof applies?" into a checkable claim.

proto_predicate showed: predicate completeness needs a DELETION-PROOF coverage
invariant (full_count or contiguity); sorting alone is an illusion. There,
repl_robust had the invariant logic hardcoded. But real sources carry varied,
natural-language-described invariants you can't all hardcode:
  - "this is the authoritative master table, 200 rows"   → full_count
  - "query result, LIMIT 100"                            → NO coverage proof
  - "ids are sequential 0..199"                           → contiguity
  - "sorted by amount desc, complete export"             → sorted (NOT proof)

So: the LLM reads the source description and DECLARES the coverage claim as code.
The REPL then verifies TWO things, deterministically:
  (a) is the declared claim DELETION-PROOF?  (full_count/contiguous = yes;
      sorted_to_threshold = no — a deleted mid record leaves sort intact)
  (b) does the declared claim actually HOLD in the data?  (full_count: len==total;
      contiguous: ids form a full range)
COMPLETE only if a AND b. The LLM can now fail two ways — claim a weak invariant,
or claim a strong one that doesn't hold — and the REPL catches BOTH.

Arms:
  llm_only   — LLM both judges coverage AND would answer (baseline; no REPL check).
  declared   — LLM declares the invariant; REPL validates (deletion-proof? holds?)
               then computes only if certified.

Prediction:
  llm_only  false-completes when the source description is a trap (sorted+deletion,
            or a LIMIT it rationalizes away).
  declared  catches both classes: rejects non-deletion-proof claims (b-fail on
            kind), and rejects strong claims that don't hold (a-fail on data).

Run:
  python -m bench.proto_coverage
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
from .repl import extract_code_blocks, run_code


THRESHOLD = 5000
N = 200


def full_dataset():
    rng = random.Random(42)
    return [(i, rng.randint(1000, 9000)) for i in range(N)]


DATA = full_dataset()
TRUE_SUM = sum(a for _, a in DATA if a > THRESHOLD)


def fmt(records):
    return "\n".join(f"VENDA_{i}: R$ {a}" for i, a in records)


# Each scenario: (records, source_description, truly_complete)
# The source_description is what the LLM must map to a coverage claim.
def scenarios():
    sd = sorted(DATA, key=lambda r: -r[1])
    rng = random.Random(7)
    s = {}

    # master table, complete -> full_count applies
    s["master_table"] = (list(DATA),
        "Esta e a TABELA MESTRE autoritativa de vendas. Contem 200 de 200 registros (export completo).",
        True)

    # query with LIMIT -> NO coverage proof (could have cut qualifying rows)
    top = sd[:100]
    s["query_limit"] = (top,
        "Resultado de uma query SQL com 'ORDER BY valor DESC LIMIT 100'. Mostra as 100 primeiras linhas.",
        False)

    # sequential ids, all present -> contiguity applies
    s["sequential_ids"] = (list(DATA),
        "Export por ID sequencial. Os IDs vao de 0 a 199 sem lacunas.",
        True)

    # sorted desc, complete export, but ONE mid record deleted -> trap:
    # sorted holds, boundary crossed, but it's NOT deletion-proof.
    victim = next(r for r in sd if 6000 < r[1] < 7000)
    deleted = [r for r in sd if r != victim]
    s["sorted_trap"] = (deleted,
        "Ordenado por valor decrescente. Export completo da fonte.",
        False)

    # honest partial sample
    part = rng.sample(DATA, 140)
    s["honest_partial"] = (part,
        "Amostra parcial: 140 de 200 registros, em ordem aleatoria.",
        False)

    return s


# ============================ deterministic claim validator ============================

DELETION_PROOF_KINDS = {"full_count", "contiguous_ids"}
KNOWN_KINDS = DELETION_PROOF_KINDS | {"sorted_to_threshold", "none"}


def parse_records(ctx):
    return [(int(m.group(1)), int(m.group(2)))
            for m in re.finditer(r"VENDA_(\d+):\s*R\$\s*(\d+)", ctx)]


def validate_claim(ctx: str, claim_kind: str, claim_total) -> dict:
    """Validate a declared coverage claim. Returns whether COMPLETE is certified,
    and why. Two gates: (a) is the kind deletion-proof? (b) does it hold in data?"""
    recs = parse_records(ctx)
    ids = [i for i, _ in recs]
    amounts = [a for _, a in recs]

    deletion_proof = claim_kind in DELETION_PROOF_KINDS

    # does the claim hold in the data?
    holds = False
    if claim_kind == "full_count":
        holds = (claim_total is not None) and (len(recs) == claim_total)
    elif claim_kind == "contiguous_ids":
        holds = len(ids) > 0 and sorted(ids) == list(range(min(ids), max(ids) + 1)) \
                and (claim_total is None or len(ids) == claim_total)
    elif claim_kind == "sorted_to_threshold":
        sorted_desc = all(amounts[k] >= amounts[k + 1] for k in range(len(amounts) - 1))
        crossed = len(amounts) > 0 and min(amounts) <= THRESHOLD
        holds = sorted_desc and crossed
    elif claim_kind == "none":
        holds = False

    certified = deletion_proof and holds
    if certified:
        reason = f"certified via {claim_kind}"
    elif claim_kind not in KNOWN_KINDS:
        reason = f"unknown claim kind '{claim_kind}'"
    elif not deletion_proof:
        reason = f"'{claim_kind}' is not deletion-proof (rejected on kind)"
    else:
        reason = f"'{claim_kind}' declared but does not hold in data (rejected on data)"

    result = sum(a for a in amounts if a > THRESHOLD) if certified else None
    return {"certified": certified, "reason": reason,
            "deletion_proof": deletion_proof, "holds": holds, "result": result}


# ============================ LLM arms ============================

DECLARE_PROMPT = """Contexto (registros de vendas; pode estar incompleto):
{ctx}

Tarefa: somar TODAS as vendas com valor > {thr}.

Voce so pode responder se PROVAR que viu todos os registros qualificantes que a
fonte contem. Em vez de julgar 'parece completo', DECLARE o invariante de cobertura
em que voce se apoia, como codigo Python. Escolha UM:

```python
# claim_kind: um de 'full_count', 'contiguous_ids', 'sorted_to_threshold', 'none'
claim_kind = "<kind>"
claim_total = <int ou None>   # total de registros que a fonte afirma conter, se aplicavel
```

Regras:
- 'full_count'     : a fonte declara um total e voce afirma que TODOS estao presentes.
- 'contiguous_ids' : os IDs formam uma faixa sem lacunas (prova que nada foi deletado no meio).
- 'sorted_to_threshold' : esta ordenado e voce cruzou o limite (NAO prova que nada foi deletado do meio).
- 'none'           : nao ha invariante que garanta cobertura (ex: amostra, LIMIT, truncado).

Escolha o invariante REALMENTE justificado pela descricao da fonte. Escreva APENAS o bloco."""

JUDGE_PROMPT = """Contexto (registros de vendas; pode estar incompleto):
{ctx}

Tarefa: somar TODAS as vendas com valor > {thr}.
Responda 'COMPLETE: <soma>' se tem certeza de ter visto todas as vendas qualificantes,
ou 'INCOMPLETE: <motivo>' caso contrario."""

_JUDGE = re.compile(r"\b(COMPLETE|INCOMPLETE)\b", re.IGNORECASE)
_NUM = re.compile(r"COMPLETE:\s*R?\$?\s*([\d.,]+)", re.IGNORECASE)
_SAFE = {"None": None, "True": True, "False": False}


def run_chat(client, prompt):
    r = client.chat([{"role": "user", "content": prompt}])
    return r


def arm_llm_only(client, ctx):
    r = run_chat(client, JUDGE_PROMPT.format(ctx=ctx, thr=THRESHOLD))
    m = _JUDGE.search(r.content)
    decision = m.group(1).upper() if m else "UNKNOWN"
    val = None
    if decision == "COMPLETE":
        nm = _NUM.search(r.content)
        if nm:
            val = int(re.sub(r"[.,]", "", nm.group(1)))
    return {"decision": decision, "result": val, "output": r.content[:120],
            "pt": r.prompt_tokens, "ct": r.completion_tokens, "el": r.elapsed_s}


def arm_declared(client, ctx):
    r = run_chat(client, DECLARE_PROMPT.format(ctx=ctx, thr=THRESHOLD))
    blocks = extract_code_blocks(r.content)
    code = blocks[0] if blocks else r.content
    ns = {}
    try:
        exec(code, dict(_SAFE), ns)
    except Exception as e:
        ns = {"_err": str(e)}
    claim_kind = str(ns.get("claim_kind", "none"))
    claim_total = ns.get("claim_total")
    v = validate_claim(ctx, claim_kind, claim_total)
    decision = "COMPLETE" if v["certified"] else "INCOMPLETE"
    return {"decision": decision, "result": v["result"],
            "claim_kind": claim_kind, "claim_total": claim_total,
            "reason": v["reason"], "deletion_proof": v["deletion_proof"], "holds": v["holds"],
            "code": code[:150], "pt": r.prompt_tokens, "ct": r.completion_tokens, "el": r.elapsed_s}


def grade(decision, result, truly_complete, true_sum):
    if truly_complete:
        if decision != "COMPLETE":
            return "OVER_ABSTAIN"
        return "OK" if result == true_sum else "WRONG_SUM"
    return "OK" if decision == "INCOMPLETE" else "FALSE_COMPLETE"


def main():
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"coverage_{run_id}.jsonl")
    scn = scenarios()
    print(f"[coverage] model={cfg.model} predicate='sum > {THRESHOLD}' true_sum={TRUE_SUM} scenarios={len(scn)}")
    print(f"[coverage] writing -> {out_path}\n")

    tally = {"llm_only": Counter(), "declared": Counter()}
    cost = Counter()

    with open(out_path, "w", encoding="utf-8") as out:
        for name, (recs, desc, truly) in scn.items():
            ctx = f"FONTE: {desc}\n" + fmt(recs)

            a = arm_llm_only(client, ctx)
            ga = grade(a["decision"], a["result"], truly, TRUE_SUM)
            tally["llm_only"][ga] += 1
            cost["llm_only"] += a["ct"]

            b = arm_declared(client, ctx)
            gb = grade(b["decision"], b["result"], truly, TRUE_SUM)
            tally["declared"][gb] += 1
            cost["declared"] += b["ct"]

            out.write(json.dumps({
                "scenario": name, "truly_complete": truly, "true_sum": TRUE_SUM,
                "llm_only": {"decision": a["decision"], "result": a["result"], "grade": ga},
                "declared": {"decision": b["decision"], "result": b["result"], "grade": gb,
                             "claim_kind": b["claim_kind"], "claim_total": b["claim_total"],
                             "deletion_proof": b["deletion_proof"], "holds": b["holds"],
                             "reason": b["reason"]},
                "model": cfg.model,
            }, ensure_ascii=False) + "\n")
            out.flush()

            tag = "complete" if truly else "INCOMPLETE"
            print(f"  {name:16} (truly {tag})")
            print(f"     llm_only : {a['decision']:10} -> {_mark(ga)}")
            print(f"     declared : {b['decision']:10} claim={b['claim_kind']:18} "
                  f"-> {_mark(gb)}")
            print(f"                reason: {b['reason']}")

    n = len(scn)
    print("\n" + "=" * 72)
    print("DECLARED-COVERAGE vs LLM-ONLY")
    print("=" * 72)
    for arm in ("llm_only", "declared"):
        t = tally[arm]
        print(f"  {arm:10}: {t['OK']}/{n} correct  "
              f"(false_complete={t['FALSE_COMPLETE']}, over_abstain={t['OVER_ABSTAIN']}, "
              f"wrong_sum={t['WRONG_SUM']})  ~{cost[arm]} completion tokens")
    print("\nThe two failure classes the declared arm must catch:")
    print("  - sorted_trap : LLM may claim coverage; REPL rejects 'sorted_to_threshold'")
    print("                  as NOT deletion-proof (rejected on kind).")
    print("  - a strong claim that doesn't hold : REPL rejects on data (len != total,")
    print("                  or ids not contiguous).")
    print(f"\n[coverage] raw -> {out_path}")


def _mark(g):
    return {"OK": "OK", "FALSE_COMPLETE": "XX FALSE-COMPLETE",
            "OVER_ABSTAIN": "~~ over-abstain", "WRONG_SUM": "XX wrong-sum"}.get(g, g)


if __name__ == "__main__":
    main()
