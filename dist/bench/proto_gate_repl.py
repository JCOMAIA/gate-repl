"""REPL-grounded gate — the fix for the SPOF found in proto_gate_adv.

The LLM gate false-passed 7/15 on subtle gaps because it judged completeness at
RANGE granularity ("300-320 looks complete") and missed interior holes. The
insight: completeness is COMPUTATION, not judgment. Count the IDs, compare to
the required count — the CPU can't miss an interior element.

New gate design (two deterministic checks, LLM only declares intent):
  Stage 1a — DECLARE: the LLM emits Python that defines `required_ids` (the exact
             set of IDs the task needs) and `tax_rate(store, id)`. It does NOT
             judge completeness.
  Stage 1b — VERIFY (deterministic harness): parse the present IDs from `context`,
             compute required_ids - present_ids. If non-empty -> FAIL (gap is the
             exact missing set). This is pure set difference, run in the REPL.
  Stage 2  — COMPUTE: only if the gap is empty, the same/declared code sums the
             taxed values from the parsed context.

We reuse the EXACT adversarial conditions from proto_gate_adv so the false-pass
rate is directly comparable: LLM-gate = 7/15, REPL-gate predicted = 0/15.

Run:
  python -m bench.proto_gate_repl
"""
import json
import os
import re
import time
from collections import Counter

from . import config, evaluator
from .client import ORClient
from .pricing import cost_usd
from .repl import extract_code_blocks, run_code
from .proto_belief import generate_variant, ground_truth, build_task
from .proto_gate_adv import ADV_VARIANTS, conditions_for, build_context, EXPECTED_PASS, TOL


DECLARE_PROMPT = """Voce tem uma variavel Python `context` (string) no ambiente,
contendo linhas no formato 'ID_<n>: Venda de R$ <valor>' de duas lojas (A e B),
mais regras de aliquota.

--- inicio de context ---
{ctx}
--- fim ---

Tarefa: {task}

NAO calcule e NAO julgue se o contexto esta completo. Apenas DECLARE a intencao
da tarefa como codigo Python. Escreva um unico bloco que define EXATAMENTE:

    # os IDs que a tarefa exige, por loja:
    required_A = set(range(<inicio_A>, <fim_A>+1))
    required_B = set(range(<inicio_B>, <fim_B>+1))
    rate_A = <aliquota_da_loja_A_como_float>
    rate_B = <aliquota_da_loja_B_como_float>

Use as faixas de ID e aliquotas exatas da tarefa e das regras. Escreva APENAS o
bloco de codigo."""


# Deterministic harness: given the LLM-declared required sets + the context,
# parse present IDs per store and compute the gap. The store of each line is
# inferred by which required set the value-pattern fits; simpler: the context
# blocks are labelled loja_A.txt / loja_B.txt, so we parse per block.
VERIFY_CODE = r"""
import re
def _present_ids(block):
    return set(int(m) for m in re.findall(r'ID_(\d+):', block))

# split context into the two store blocks by their headers
parts = re.split(r'---\s*loja_([AB])\.txt[^\n]*---', context)
# re.split keeps the captured 'A'/'B' between blocks: [pre, 'A', blockA, 'B', blockB]
present_A = set(); present_B = set()
for i in range(1, len(parts) - 1, 2):
    store = parts[i]; block = parts[i + 1]
    if store == 'A': present_A |= _present_ids(block)
    elif store == 'B': present_B |= _present_ids(block)

gap_A = sorted(required_A - present_A)
gap_B = sorted(required_B - present_B)
if gap_A or gap_B:
    print(f'GATE: FAIL missing_A={gap_A} missing_B={gap_B}')
else:
    # compute deterministically since gate passes
    def _val(block, ids):
        out = {}
        for m in re.finditer(r'ID_(\d+): Venda de R\$ (\d+)', block):
            i = int(m.group(1))
            if i in ids: out[i] = int(m.group(2))
        return out
    valsA = {}; valsB = {}
    for i in range(1, len(parts) - 1, 2):
        store = parts[i]; block = parts[i + 1]
        if store == 'A': valsA.update(_val(block, required_A))
        elif store == 'B': valsB.update(_val(block, required_B))
    total = sum(v * rate_A for v in valsA.values()) + sum(v * rate_B for v in valsB.values())
    print(f'GATE: PASS')
    print(f'FINAL: {total}')
"""


def run_one(client, prompt):
    r = client.chat([{"role": "user", "content": prompt}])
    return {"output": r.content, "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens, "elapsed_s": r.elapsed_s,
            "ok": r.ok, "error": r.error}


_GATE = re.compile(r"GATE\s*:\s*(PASS|FAIL)", re.IGNORECASE)


def run_repl_gate(client, ctx, task, gt, workspace_dir):
    # Stage 1a: LLM declares required sets + rates as code
    d = run_one(client, DECLARE_PROMPT.format(ctx=ctx, task=task))
    blocks = extract_code_blocks(d["output"])
    declare_code = blocks[0] if blocks else d["output"]

    # Stage 1b + 2: run declare + deterministic verify/compute together
    full_code = declare_code + "\n" + VERIFY_CODE
    repl_out = run_code(full_code, workspace_dir, glb={"context": ctx})

    gm = _GATE.search(repl_out)
    decision = gm.group(1).upper() if gm else "ERROR"
    final_value = evaluator.extract_final_number(repl_out) if decision == "PASS" else None

    return {
        "gate": decision,
        "final_value": final_value,
        "final_correct": evaluator.matches(final_value, gt, tol=TOL),
        "prompt_tokens": d["prompt_tokens"], "completion_tokens": d["completion_tokens"],
        "elapsed_s": d["elapsed_s"],
        "cost_usd": cost_usd(client.model, d["prompt_tokens"], d["completion_tokens"]),
        "declare_code": declare_code[:300],
        "repl_output": repl_out[:300],
    }


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"gaterepl_{run_id}.jsonl")
    cond_names = ["complete", "drop_mid", "drop_last", "drop_pair"]
    total = len(ADV_VARIANTS) * len(cond_names)
    print(f"[gaterepl] model={cfg.model} ({total} gate evals, REPL-grounded)")
    print(f"[gaterepl] writing -> {out_path}")

    gate_by_cond: dict[str, Counter] = {c: Counter() for c in cond_names}
    harm_by_cond: dict[str, Counter] = {c: Counter() for c in cond_names}

    with open(out_path, "w", encoding="utf-8") as out:
        for vi, v in enumerate(ADV_VARIANTS):
            generate_variant("workspace", v)
            gt = ground_truth(v)
            task = build_task(v)
            conds = conditions_for(v)
            for cname in cond_names:
                ctx = build_context(v, conds[cname])
                res = run_repl_gate(client, ctx, task, gt, "workspace")
                res.update({"variant": v, "variant_idx": vi, "condition": cname,
                            "ground_truth": gt, "expected_pass": EXPECTED_PASS[cname],
                            "model": cfg.model})
                gate_by_cond[cname][res["gate"]] += 1
                if res["gate"] == "FAIL":
                    harm = "ABSTAINED"
                elif res["gate"] == "ERROR":
                    harm = "GATE_ERROR"
                elif res["final_correct"]:
                    harm = "PASS_CORRECT"
                else:
                    harm = "PASS_WRONG"
                res["harm"] = harm
                harm_by_cond[cname][harm] += 1
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                out.flush()
                flag = ""
                if cname != "complete" and res["gate"] == "PASS":
                    flag = "  <-- FALSE-PASS"
                if cname == "complete" and res["gate"] != "PASS":
                    flag = f"  <-- gate={res['gate']} on complete"
                print(f"  v{vi} [{cname:10}] gate={res['gate']:6} harm={harm:12} "
                      f"final={res['final_value']}{flag}")

    n = len(ADV_VARIANTS)
    print("\n" + "=" * 76)
    print("REPL-GATE DECISION BY CONDITION")
    print("=" * 76)
    print(f"{'condition':12}{'should':8}{'PASS':>6}{'FAIL':>6}{'ERROR':>7}   verdict")
    for cname in cond_names:
        gc = gate_by_cond[cname]
        should = "PASS" if EXPECTED_PASS[cname] else "FAIL"
        if EXPECTED_PASS[cname]:
            bad = gc["FAIL"] + gc["ERROR"]
            verdict = "OK" if bad == 0 else f"{bad}/{n} wrong-FAIL/ERROR"
        else:
            bad = gc["PASS"]
            verdict = "OK (caught all)" if bad == 0 else f"{bad}/{n} FALSE-PASS"
        print(f"{cname:12}{should:8}{gc['PASS']:>6}{gc['FAIL']:>6}{gc['ERROR']:>7}   {verdict}")

    false_pass = sum(gate_by_cond[c]["PASS"] for c in cond_names if not EXPECTED_PASS[c])
    gap_total = sum(n for c in cond_names if not EXPECTED_PASS[c])
    print("\n" + "=" * 76)
    print("SPOF COMPARISON")
    print("=" * 76)
    print(f"  LLM-gate  FALSE-PASS (proto_gate_adv): 7/15")
    print(f"  REPL-gate FALSE-PASS (this run):       {false_pass}/{gap_total}")
    print("\nDownstream harm by condition:")
    for cname in cond_names:
        hc = harm_by_cond[cname]
        print(f"  {cname:10}: " + " ".join(f"{k}={v}" for k, v in sorted(hc.items())))
    print(f"\n[gaterepl] raw -> {out_path}")


if __name__ == "__main__":
    main()
