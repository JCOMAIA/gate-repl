"""Self-consistency repair loop — the generalist fix for declaration slips.

proto_coverage2 found: when the LLM mis-declares (e.g. puts the answer value in
claim_total instead of the record count), the validator rejected to the SAFE side
(over-abstain) — correct, but it needlessly refused a decidable task. The lazy fix
would special-case claim_total. The generalist fix follows the project's principle:
don't trust the declared field, and don't blindly reject it either — CHECK it for
internal consistency against the data, and if it's incoherent, return a precise
diagnostic so the LLM can CORRECT it, then re-decide.

This adds the third side of the guarantee:
  * never false-completes            (had it)
  * abstains honestly when undecidable (had it)
  * does NOT refuse a correctable declaration slip   (this)

Mechanism: declare -> check_consistency -> (if incoherent) feed diagnostic back ->
re-declare -> ... up to MAX_REPAIRS -> then validate+decide. The consistency check
is GENERIC: it flags any declared field that cannot be reconciled with the parsed
data, not a specific field.

Test design: inject declaration slips on purpose (a "buggy" declarer that mangles
the total / kind) and verify the loop recovers them WITHOUT ever false-completing.

Run:
  python -m bench.proto_coverage3
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
MAX_REPAIRS = 2


def full_dataset():
    rng = random.Random(42)
    return [(i, rng.randint(1000, 9000)) for i in range(N)]


DATA = full_dataset()
TRUE_SUM = sum(a for _, a in DATA if a > THRESHOLD)
_frng = random.Random(99)
FLAGGED = set(_frng.sample(range(N), 30))
TRUE_FLAGGED_SUM = sum(a for i, a in DATA if i in FLAGGED)

DELETION_PROOF = {"full_count", "contiguous_ids"}
KNOWN = DELETION_PROOF | {"sorted_to_threshold", "none", "undecidable"}


def parse_records(ctx):
    out = []
    for m in re.finditer(r"VENDA_(\d+):\s*R\$\s*(\d+)(?:\s*\|\s*flag=(SIM|NAO))?", ctx):
        out.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    return out


# ============================ generic consistency check ============================

def predicate_evaluable(ctx, predicate) -> bool:
    """Deterministic: can the predicate be evaluated from the present records at
    all? sum_gt always can (amount is in the record); flagged_sum only if a flag
    field is present."""
    recs = parse_records(ctx)
    has_flag = any(f is not None for _, _, f in recs)
    return predicate == "sum_gt" or (predicate == "flagged_sum" and has_flag)


def check_consistency(ctx, claim_kind, claim_total, predicate=None) -> tuple[bool, str]:
    """GENERIC: is the declaration internally coherent with the parsed data?
    Returns (coherent, diagnostic). Does NOT decide completeness — only flags a
    declaration that cannot be reconciled, so the LLM can fix it.

    Coherence rules (all general, none field-specific to one scenario):
      1. claim_kind must be a known kind.
      2. FORM slip: a declared total must be plausibly a RECORD COUNT, not an
         aggregate of the values (the mis-placed-answer slip), and not below the
         present count.
      3. full_count REQUIRES a total; contiguous_ids total must match id-span.
      4. UNDUE UNDECIDABLE (judgment, made checkable): declaring 'undecidable' is
         only coherent when the predicate genuinely CANNOT be evaluated from the
         records. If it can (e.g. sum_gt, or flagged_sum with a flag field),
         'undecidable' is wrong — reject and ask for a coverage invariant. This
         closes the form/judgment gap: decide() already knows evaluability, so the
         consistency gate can use it.
    """
    recs = parse_records(ctx)
    present = len(recs)
    amounts = [a for _, a, _ in recs]
    ids = [i for i, _, _ in recs]

    if claim_kind not in KNOWN:
        return False, f"claim_kind '{claim_kind}' is not one of {sorted(KNOWN)}."

    if claim_kind == "undecidable" and predicate is not None and predicate_evaluable(ctx, predicate):
        return False, (f"declared 'undecidable', but the predicate '{predicate}' IS evaluable from the "
                       f"present records (the needed field is here). Re-declare a coverage invariant "
                       f"(full_count / contiguous_ids) instead of undecidable.")

    if claim_kind == "full_count":
        if claim_total is None:
            return False, "claim_kind='full_count' requires claim_total (the source's record count)."
        if claim_total < present:
            return False, (f"claim_total={claim_total} is below the {present} records actually present; "
                           f"a source total cannot be fewer than what you see.")
        # is the declared 'total' actually an aggregate of the data (mis-placed answer)?
        sum_gt = sum(a for a in amounts if a > THRESHOLD)
        sum_all = sum(amounts)
        flagged_sum = sum(a for i, a, f in recs if f == "SIM")
        if claim_total in {sum_gt, sum_all, flagged_sum} and claim_total > 5 * max(present, 1):
            return False, (f"claim_total={claim_total} equals an aggregate of the values, not a record "
                           f"count. There are {present} records; claim_total should be the SOURCE's "
                           f"record count (e.g. {present} if complete), not a sum.")

    if claim_kind == "contiguous_ids" and claim_total is not None:
        span = (max(ids) - min(ids) + 1) if ids else 0
        if claim_total != span and claim_total != present:
            return False, (f"claim_kind='contiguous_ids' but claim_total={claim_total} matches neither the "
                           f"id-span ({span}) nor the present count ({present}).")

    return True, "coherent"


# ============================ decide (post-consistency) ============================

def decide(ctx, claim_kind, claim_total, predicate) -> dict:
    """Same validator as coverage2, run only AFTER the declaration is coherent."""
    recs = parse_records(ctx)
    ids = [i for i, _, _ in recs]
    has_flag = any(f is not None for _, _, f in recs)

    if claim_kind == "undecidable":
        evaluable = (predicate == "sum_gt") or has_flag
        return {"verdict": "UNDECIDABLE" if not evaluable else "INCOMPLETE",
                "result": None,
                "reason": "predicate not evaluable from records" if not evaluable
                          else "declared undecidable but predicate is evaluable"}

    if predicate == "flagged_sum" and not has_flag:
        return {"verdict": "UNDECIDABLE", "result": None,
                "reason": "predicate needs a flag field absent from records"}

    deletion_proof = claim_kind in DELETION_PROOF
    holds = False
    if claim_kind == "full_count":
        holds = claim_total is not None and len(recs) == claim_total
    elif claim_kind == "contiguous_ids":
        holds = bool(ids) and sorted(ids) == list(range(min(ids), max(ids) + 1)) \
                and (claim_total is None or len(ids) == claim_total)
    elif claim_kind == "sorted_to_threshold":
        amts = [a for _, a, _ in recs]
        holds = all(amts[k] >= amts[k+1] for k in range(len(amts)-1)) and (amts and min(amts) <= THRESHOLD)

    if not (deletion_proof and holds):
        return {"verdict": "INCOMPLETE", "result": None,
                "reason": f"'{claim_kind}' " + ("not deletion-proof" if not deletion_proof else "does not hold")}
    result = (sum(a for _, a, _ in recs if a > THRESHOLD) if predicate == "sum_gt"
              else sum(a for _, a, f in recs if f == "SIM"))
    return {"verdict": "COMPLETE", "result": result, "reason": f"certified via {claim_kind}"}


# ============================ declarer (LLM) with injectable bug ============================

DECLARE_PROMPT = """Contexto:
{ctx}

Aplique o predicado a TODOS os registros qualificantes; so responda se a COBERTURA
puder ser PROVADA. Declare como codigo:
```python
# claim_kind: 'full_count' | 'contiguous_ids' | 'sorted_to_threshold' | 'none' | 'undecidable'
claim_kind = "<kind>"
claim_total = <int ou None>   # o NUMERO DE REGISTROS que a fonte afirma conter (NAO um valor/soma)
```
{repair}
Escreva APENAS o bloco."""

_SAFE = {"None": None, "True": True, "False": False}


def llm_declare(client, ctx, repair_msg=""):
    rep = f"\nCORRECAO NECESSARIA: {repair_msg}\n" if repair_msg else ""
    r = client.chat([{"role": "user", "content": DECLARE_PROMPT.format(ctx=ctx, repair=rep)}])
    blocks = extract_code_blocks(r.content)
    code = blocks[0] if blocks else r.content
    ns = {}
    try:
        exec(code, dict(_SAFE), ns)
    except Exception:
        ns = {}
    return str(ns.get("claim_kind", "none")), ns.get("claim_total"), r.prompt_tokens, r.completion_tokens


def source_claimed_total(ctx):
    """The total the SOURCE asserts (from its label, e.g. '200 de 200') — NOT the
    count of records you happen to see. A correct repair must use this, never the
    present count, or a partial source would be wrongly certified complete."""
    m = re.search(r"(\d+)\s+de\s+(\d+)", ctx)
    return int(m.group(2)) if m else None


def buggy_declare(client, ctx, repair_msg, predicate):
    """Simulates a model that, on the FIRST try, mis-places the answer value into
    claim_total (the exact coverage2 slip). On repair, it declares correctly by
    reading the SOURCE'S claimed total (from the label), NOT the present count —
    this isolates whether the LOOP recovers the slip without ever inventing a total
    from what's visible (which would re-introduce false-complete on partial data)."""
    recs = parse_records(ctx)
    has_flag = any(f is not None for _, _, f in recs)
    if not repair_msg:
        ans = (sum(a for _, a, f in recs if f == "SIM") if predicate == "flagged_sum" and has_flag
               else sum(a for _, a, _ in recs if a > THRESHOLD))
        return "full_count", ans, 0, 0
    # honest repair: declare the SOURCE's claimed total, not len(present)
    return "full_count", source_claimed_total(ctx), 0, 0


# ============================ scenarios ============================

def scenarios():
    s = {}
    # decidable & complete, predicate sum_gt -> the slip-prone case
    s["sum_full"] = (list(DATA), "TABELA MESTRE: 200 de 200 registros.", "sum_gt", "complete")
    # decidable & complete, flagged with field
    s["flag_full"] = ("WITH_FIELD", "TABELA MESTRE: 200 de 200 registros, com campo flag.", "flagged_sum", "complete")
    # genuinely incomplete (must stay INCOMPLETE no matter how declared)
    rng = random.Random(7)
    s["partial"] = (rng.sample(DATA, 140), "Amostra: 140 de 200.", "sum_gt", "incomplete")
    # undecidable (flag external)
    s["flag_external"] = (list(DATA), "TABELA MESTRE: 200 de 200. (flag vem de auditoria externa.)",
                          "flagged_sum", "undecidable")
    return s


def build_context(records):
    if records == "WITH_FIELD":
        return "\n".join(f"VENDA_{i}: R$ {a} | flag={'SIM' if i in FLAGGED else 'NAO'}" for i, a in DATA)
    return "\n".join(f"VENDA_{i}: R$ {a}" for i, a in records)


def run_with_repair(arm, client, ctx, predicate):
    """The loop: declare -> consistency-check -> (repair)* -> decide.
    `arm` is 'llm' (real model) or 'buggy_first' (always slips on attempt 1)."""
    trace = []
    repair_msg = ""
    pt = ct = 0
    kind, total = "none", None
    for attempt in range(MAX_REPAIRS + 1):
        if arm == "buggy_first":
            kind, total, p, c = buggy_declare(client, ctx, repair_msg, predicate)
        else:
            kind, total, p, c = llm_declare(client, ctx, repair_msg)
        pt += p; ct += c
        coherent, diag = check_consistency(ctx, kind, total, predicate)
        trace.append({"attempt": attempt, "kind": kind, "total": total,
                      "coherent": coherent, "diag": diag})
        if coherent:
            break
        repair_msg = diag
    d = decide(ctx, kind, total, predicate)
    return {"verdict": d["verdict"], "result": d["result"], "reason": d["reason"],
            "attempts": len(trace), "trace": trace, "pt": pt, "ct": ct,
            "final_kind": kind, "final_total": total}


def grade(verdict, truth):
    want = {"complete": "COMPLETE", "incomplete": "INCOMPLETE", "undecidable": "UNDECIDABLE"}[truth]
    return "OK" if verdict == want else f"WRONG({verdict})"


def main():
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"coverage3_{run_id}.jsonl")
    scn = scenarios()
    print(f"[coverage3] model={cfg.model} self-consistency repair loop (max {MAX_REPAIRS})")
    print(f"[coverage3] writing -> {out_path}\n")

    # Two declarer arms: the real LLM, and a buggy declarer that always slips first.
    arms = ["llm", "buggy_first"]
    tally = {a: Counter() for a in arms}

    with open(out_path, "w", encoding="utf-8") as out:
        for name, (recs, desc, predicate, truth) in scn.items():
            ctx = f"FONTE: {desc}\nPREDICADO: {predicate}\n" + build_context(recs)
            print(f"  {name:14} (truth {truth}, predicate {predicate})")
            for arm in arms:
                res = run_with_repair(arm, client, ctx, predicate)
                g = grade(res["verdict"], truth)
                tally[arm]["OK" if g == "OK" else "WRONG"] += 1
                if res["verdict"] == "COMPLETE" and truth != "complete":
                    tally[arm]["FALSE_COMPLETE"] += 1
                out.write(json.dumps({"scenario": name, "arm": arm, "truth": truth,
                                      "verdict": res["verdict"], "result": res["result"],
                                      "attempts": res["attempts"], "trace": res["trace"],
                                      "final_kind": res["final_kind"], "final_total": res["final_total"],
                                      "grade": g, "model": cfg.model}, ensure_ascii=False) + "\n")
                out.flush()
                recovered = " (recovered via repair)" if res["attempts"] > 1 and g == "OK" else ""
                print(f"     {arm:12}: {res['verdict']:12} attempts={res['attempts']} "
                      f"final_total={res['final_total']} -> {g}{recovered}")

    print("\n" + "=" * 72)
    print("SELF-CONSISTENCY REPAIR — results")
    print("=" * 72)
    n = len(scn)
    for arm in arms:
        t = tally[arm]
        print(f"  {arm:12}: {t['OK']}/{n} correct   false_complete={t['FALSE_COMPLETE']}")
    print("\nKey claims:")
    print("  - buggy_first ALWAYS mis-declares on attempt 1 (answer in claim_total).")
    print("    If it reaches OK, the repair LOOP recovered it — not model luck.")
    print("  - No arm should ever FALSE_COMPLETE: the loop fixes correctable slips")
    print("    but the decide() gate still never certifies an incomplete scenario.")
    print(f"\n[coverage3] raw -> {out_path}")


if __name__ == "__main__":
    main()
