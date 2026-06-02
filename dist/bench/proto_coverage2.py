"""Two open frontiers of predicate coverage:

  (A) ADVERSARIAL SOURCE DESCRIPTIONS — a lying label. The source says "complete
      export, 200 rows" but actually ships 140. Does the declared+validated gate
      still hold when the LLM is fed a false premise? The key: the LLM may believe
      the label and declare full_count=200, but the REPL's DATA gate checks
      len(records) against the claimed total — a lie about completeness cannot
      survive an actual count. This tests that the *data gate*, not the LLM's
      trust, carries the guarantee.

  (B) THE UNDECIDABLE CASE — a predicate whose qualifying set cannot be bounded by
      any invariant present in the data. "Every customer FLAGGED in the external
      audit": flagged-ness is not derivable from the records themselves, and no
      count/contiguity/sort over the visible fields bounds it. An honest system
      must return UNDECIDABLE (cannot prove coverage either way) — distinct from
      INCOMPLETE (proved a gap) and COMPLETE (proved coverage). Certifying OR
      blindly refusing both miss the point; the right output is "I cannot decide
      completeness from what's available; here is what would be needed."

Arms:
  declared    — LLM declares claim_kind (+ total); REPL validates kind + data.
                Now also accepts claim_kind='undecidable' as a first-class answer.

Outcomes per scenario: COMPLETE / INCOMPLETE / UNDECIDABLE, graded against truth.

Run:
  python -m bench.proto_coverage2
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
from .repl import extract_code_blocks


THRESHOLD = 5000
N = 200


def full_dataset():
    rng = random.Random(42)
    return [(i, rng.randint(1000, 9000)) for i in range(N)]


DATA = full_dataset()
TRUE_SUM = sum(a for _, a in DATA if a > THRESHOLD)

# For the undecidable predicate: a hidden "flagged" set the records don't reveal.
_frng = random.Random(99)
FLAGGED = set(_frng.sample(range(N), 30))
TRUE_FLAGGED_SUM = sum(a for i, a in DATA if i in FLAGGED)


def fmt(records):
    return "\n".join(f"VENDA_{i}: R$ {a}" for i, a in records)


def fmt_with_flag(records):
    # records carry NO flag field — flagged-ness lives in an external audit
    return "\n".join(f"VENDA_{i}: R$ {a}" for i, a in records)


# ---- scenarios: (records, source_desc, predicate, truth) ----
# truth ∈ {"complete", "incomplete", "undecidable"}
# predicate ∈ {"sum_gt", "flagged_sum"}
def scenarios():
    s = {}
    rng = random.Random(7)

    # --- group A: adversarial / honest labels, predicate = sum > THRESHOLD ---
    # A1: label LIES "complete 200" but only 140 present -> truth incomplete; data gate must catch
    part = rng.sample(DATA, 140)
    s["lying_label"] = (part,
        "TABELA MESTRE completa e autoritativa: 200 de 200 registros.",  # LIE
        "sum_gt", "incomplete")

    # A2: label honest "complete 200", all present -> complete
    s["honest_full"] = (list(DATA),
        "TABELA MESTRE completa e autoritativa: 200 de 200 registros.",
        "sum_gt", "complete")

    # A3: label says "complete" but ids 0..199 with one mid-deleted; count claim
    #     would be 200 but only 199 present -> incomplete, data gate catches
    victim = next(i for i in range(N) if i in {97})
    deleted = [(i, a) for i, a in DATA if i != victim]
    s["lying_count_contig"] = (deleted,
        "Export completo por ID sequencial: IDs 0 a 199, 200 registros.",  # count lies
        "sum_gt", "incomplete")

    # --- group B: undecidable predicate = sum of FLAGGED customers ---
    # B1: all 200 records present, but flagged-ness is EXTERNAL -> cannot prove which
    #     are flagged from the records -> UNDECIDABLE (even with full_count!)
    s["flagged_full_records"] = (list(DATA),
        "TABELA MESTRE de vendas completa: 200 de 200 registros. (O status 'flagged' "
        "vem de uma auditoria externa NAO incluida aqui.)",
        "flagged_sum", "undecidable")

    # B2: records include an explicit flag field -> now decidable & complete
    s["flagged_with_field"] = ("WITH_FIELD",  # special: built in build_context
        "TABELA MESTRE completa: 200 de 200 registros, com campo 'flag' por registro.",
        "flagged_sum", "complete")

    return s


def build_context(name, records, desc, predicate):
    if records == "WITH_FIELD":
        lines = [f"VENDA_{i}: R$ {a} | flag={'SIM' if i in FLAGGED else 'NAO'}"
                 for i, a in DATA]
        body = "\n".join(lines)
    else:
        body = fmt(records)
    return f"FONTE: {desc}\nPREDICADO: {predicate}\n{body}"


# ============================ deterministic validator ============================

DELETION_PROOF = {"full_count", "contiguous_ids"}
KNOWN = DELETION_PROOF | {"sorted_to_threshold", "none", "undecidable"}


def parse_records(ctx):
    out = []
    for m in re.finditer(r"VENDA_(\d+):\s*R\$\s*(\d+)(?:\s*\|\s*flag=(SIM|NAO))?", ctx):
        flag = m.group(3)
        out.append((int(m.group(1)), int(m.group(2)), flag))
    return out


def parse_total(ctx):
    m = re.search(r"(\d+)\s+de\s+(\d+)", ctx)
    return int(m.group(2)) if m else None


def validate(ctx, claim_kind, claim_total, predicate):
    recs = parse_records(ctx)
    ids = [i for i, _, _ in recs]
    has_flag_field = any(f is not None for _, _, f in recs)

    # UNDECIDABLE is certified only if the predicate genuinely can't be evaluated
    # from the records AND no invariant could bound it. For flagged_sum without a
    # flag field, membership is not derivable -> declaring 'undecidable' is correct.
    if claim_kind == "undecidable":
        predicate_evaluable = (predicate == "sum_gt") or has_flag_field
        # correct to declare undecidable ONLY when predicate is not evaluable
        certified_undecidable = not predicate_evaluable
        return {"verdict": "UNDECIDABLE" if certified_undecidable else "INCOMPLETE",
                "reason": ("undecidable: predicate not evaluable from records"
                           if certified_undecidable else
                           "declared undecidable but predicate IS evaluable -> not a valid claim"),
                "result": None}

    # for flagged_sum, even a deletion-proof invariant doesn't help if the flag
    # field is absent: you can't evaluate the predicate at all.
    if predicate == "flagged_sum" and not has_flag_field:
        return {"verdict": "UNDECIDABLE_MISSED",
                "reason": "predicate needs flag field that is absent; coverage invariant is irrelevant",
                "result": None}

    deletion_proof = claim_kind in DELETION_PROOF
    holds = False
    if claim_kind == "full_count":
        holds = claim_total is not None and len(recs) == claim_total
    elif claim_kind == "contiguous_ids":
        holds = len(ids) > 0 and sorted(ids) == list(range(min(ids), max(ids) + 1)) \
                and (claim_total is None or len(ids) == claim_total)
    elif claim_kind == "sorted_to_threshold":
        amts = [a for _, a, _ in recs]
        holds = all(amts[k] >= amts[k+1] for k in range(len(amts)-1)) and (amts and min(amts) <= THRESHOLD)

    certified = deletion_proof and holds
    if not certified:
        reason = (f"'{claim_kind}' not deletion-proof" if not deletion_proof
                  else f"'{claim_kind}' does not hold in data")
        return {"verdict": "INCOMPLETE", "reason": reason, "result": None}

    # compute the predicate
    if predicate == "sum_gt":
        result = sum(a for _, a, _ in recs if a > THRESHOLD)
    else:  # flagged_sum with field present
        result = sum(a for _, a, f in recs if f == "SIM")
    return {"verdict": "COMPLETE", "reason": f"certified via {claim_kind}", "result": result}


# ============================ LLM declaration arm ============================

DECLARE_PROMPT = """Contexto:
{ctx}

A tarefa exige aplicar o predicado a TODOS os registros qualificantes que a fonte
contem, e so responder se a COBERTURA puder ser PROVADA. Declare como codigo:

```python
# claim_kind, escolha UM:
#   'full_count'          : a fonte declara um total e todos estao presentes
#   'contiguous_ids'      : os IDs formam faixa sem lacunas (nada deletado no meio)
#   'sorted_to_threshold' : ordenado e cruzou o limite (NAO prova ausencia de delecao)
#   'none'                : ha lacuna ou nenhum invariante garante cobertura
#   'undecidable'         : o predicado NAO pode ser avaliado a partir dos registros
#                           (ex: depende de dado externo ausente) — cobertura indecidivel
claim_kind = "<kind>"
claim_total = <int ou None>
```

IMPORTANTE: se o predicado depende de informacao que NAO esta nos registros
(ex: um status que vem de fonte externa nao incluida), a resposta correta e
'undecidable', NAO 'none' nem um numero. Escreva APENAS o bloco."""

_SAFE = {"None": None, "True": True, "False": False}


def arm_declared(client, ctx, predicate):
    r = client.chat([{"role": "user", "content": DECLARE_PROMPT.format(ctx=ctx)}])
    blocks = extract_code_blocks(r.content)
    code = blocks[0] if blocks else r.content
    ns = {}
    try:
        exec(code, dict(_SAFE), ns)
    except Exception as e:
        ns = {"_err": str(e)}
    kind = str(ns.get("claim_kind", "none"))
    total = ns.get("claim_total")
    v = validate(ctx, kind, total, predicate)
    return {"claim_kind": kind, "claim_total": total, **v,
            "pt": r.prompt_tokens, "ct": r.completion_tokens, "el": r.elapsed_s}


def grade(verdict, truth):
    """truth ∈ {complete, incomplete, undecidable}; verdict from validator."""
    if truth == "complete":
        return "OK" if verdict == "COMPLETE" else f"WRONG({verdict})"
    if truth == "incomplete":
        return "OK" if verdict == "INCOMPLETE" else f"WRONG({verdict})"
    if truth == "undecidable":
        return "OK" if verdict == "UNDECIDABLE" else f"WRONG({verdict})"
    return f"WRONG({verdict})"


def main():
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"coverage2_{run_id}.jsonl")
    scn = scenarios()
    print(f"[coverage2] model={cfg.model} scenarios={len(scn)} "
          f"(adversarial labels + undecidable predicate)")
    print(f"[coverage2] writing -> {out_path}\n")

    tally = Counter()
    with open(out_path, "w", encoding="utf-8") as out:
        for name, (recs, desc, predicate, truth) in scn.items():
            ctx = build_context(name, recs, desc, predicate)
            b = arm_declared(client, ctx, predicate)
            g = grade(b["verdict"], truth)
            tally["OK" if g == "OK" else "WRONG"] += 1
            out.write(json.dumps({
                "scenario": name, "truth": truth, "predicate": predicate,
                "claim_kind": b["claim_kind"], "claim_total": b["claim_total"],
                "verdict": b["verdict"], "reason": b["reason"], "result": b["result"],
                "grade": g, "model": cfg.model,
            }, ensure_ascii=False) + "\n")
            out.flush()
            print(f"  {name:22} truth={truth:11} claim={b['claim_kind']:14} "
                  f"-> {b['verdict']:16} {('OK' if g=='OK' else g)}")
            print(f"       {b['reason']}")

    print("\n" + "=" * 74)
    print("ADVERSARIAL LABELS + UNDECIDABLE — declared coverage")
    print("=" * 74)
    n = len(scn)
    print(f"  Correct: {tally['OK']}/{n}")
    print("\nWhat each group proves:")
    print("  A (lying labels): the DATA gate, not the LLM's trust of the label,")
    print("    carries the guarantee — a false 'complete 200' fails len==total.")
    print("  B (undecidable): an honest system returns UNDECIDABLE when the predicate")
    print("    can't be evaluated from the records — distinct from INCOMPLETE.")
    print(f"\n[coverage2] raw -> {out_path}")


if __name__ == "__main__":
    main()
