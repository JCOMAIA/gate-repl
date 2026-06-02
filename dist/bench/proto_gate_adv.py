"""Adversarial gate test — probing the pipeline's single point of failure.

The sequential pipeline (proto_pipeline) is only as safe as its gate. If the
gate FALSE-PASSES — declares the context complete when it has a subtle hole —
the REPL then computes over incomplete data and confabulates *with the authority
of execution*. That is the worst failure: a confidently wrong number that looks
deterministic.

The earlier `insufficient` regime removed WHOLE ranges (loja_B entirely gone) —
trivial to detect. This probes SUBTLE gaps: a single missing ID in the middle of
an otherwise-complete range. A robust gate must still notice "ID_225 is missing
between 224 and 226".

Primary metric is the GATE DECISION itself, not the final answer. (Our data is
formulaic — ID_N: R$ N*15 — so a model could reconstruct a missing value from the
pattern, masking downstream harm. The gate's job is to NOTICE the hole; whether
the REPL can paper over it is a separate question we also record.)

Conditions (all built from the full oracle context, then mutated):
  complete    — no gap. Gate SHOULD pass. (PASS rate; a FAIL here = over-paranoia)
  drop_mid    — one ID removed from the middle of range A. Gate SHOULD fail.
  drop_last   — the last ID of range A removed (boundary hole). Gate SHOULD fail.
  drop_pair   — two adjacent IDs removed from range B. Gate SHOULD fail.

A gate PASS on any drop_* condition is a FALSE-PASS — the SPOF firing.

Run:
  python -m bench.proto_gate_adv
"""
import json
import os
import time
from collections import Counter

from . import config, evaluator
from .client import ORClient
from .pricing import cost_usd
from .repl import extract_code_blocks, run_code
from .proto_pipeline import GATE_PROMPT, COMPUTE_PROMPT, gate_decision, run_one
from .proto_belief import generate_variant, ground_truth, build_task


# Use a few mid-size variants so a "middle" ID exists and ranges are long enough
# for a single missing line to be genuinely subtle.
ADV_VARIANTS = [
    (200, 220, 400, 420),
    (100, 120, 600, 620),
    (300, 320, 500, 520),
    (50, 70, 700, 720),
    (400, 420, 250, 270),
]
TOL = 1.0


def _line_a(i: int) -> str:
    return f"ID_{i}: Venda de R$ {i * 15}"


def _line_b(i: int) -> str:
    return f"ID_{i}: Venda de R$ {i * 22}"


def build_context(v, drop: set[tuple[str, int]]) -> str:
    """Full oracle context with specified (store, id) lines removed.
    `drop` is a set like {("A", 210)} or {("B", 510), ("B", 511)}."""
    a_lo, a_hi, b_lo, b_hi = v
    with open(os.path.join("workspace", "taxas.txt"), encoding="utf-8") as f:
        rules = f.read()
    a_lines = [_line_a(i) for i in range(a_lo, a_hi + 1) if ("A", i) not in drop]
    b_lines = [_line_b(i) for i in range(b_lo, b_hi + 1) if ("B", i) not in drop]
    return (
        f"--- taxas.txt ---\n{rules}\n\n"
        f"--- loja_A.txt (IDs {a_lo}-{a_hi}) ---\n" + "\n".join(a_lines) + "\n\n"
        f"--- loja_B.txt (IDs {b_lo}-{b_hi}) ---\n" + "\n".join(b_lines)
    )


def conditions_for(v) -> dict[str, set]:
    a_lo, a_hi, b_lo, b_hi = v
    a_mid = (a_lo + a_hi) // 2
    b_mid = (b_lo + b_hi) // 2
    return {
        "complete": set(),
        "drop_mid": {("A", a_mid)},
        "drop_last": {("A", a_hi)},
        "drop_pair": {("B", b_mid), ("B", b_mid + 1)},
    }


# What the gate SHOULD do per condition.
EXPECTED_PASS = {"complete": True, "drop_mid": False, "drop_last": False, "drop_pair": False}


def run_gate_and_maybe_compute(client, ctx, task, gt, workspace_dir):
    g = run_one(client, GATE_PROMPT.format(ctx=ctx, task=task))
    decision = gate_decision(g["output"])
    pt, ct, el = g["prompt_tokens"], g["completion_tokens"], g["elapsed_s"]

    final_value = None
    compute_out = ""
    if decision != "FAIL":  # PASS or UNKNOWN → it would proceed to compute
        c = run_one(client, COMPUTE_PROMPT.format(ctx=ctx, task=task))
        pt += c["prompt_tokens"]; ct += c["completion_tokens"]; el += c["elapsed_s"]
        blocks = extract_code_blocks(c["output"])
        code = blocks[0] if blocks else c["output"]
        compute_out = run_code(code, workspace_dir, glb={"context": ctx})
        final_value = evaluator.extract_final_number(compute_out)

    return {
        "gate": decision,
        "final_value": final_value,
        "final_correct": evaluator.matches(final_value, gt, tol=TOL),
        "prompt_tokens": pt, "completion_tokens": ct, "elapsed_s": el,
        "cost_usd": cost_usd(client.model, pt, ct),
        "gate_output": g["output"][:350],
        "compute_output": compute_out[:200],
    }


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"gateadv_{run_id}.jsonl")
    cond_names = ["complete", "drop_mid", "drop_last", "drop_pair"]
    total = len(ADV_VARIANTS) * len(cond_names)
    print(f"[gateadv] model={cfg.model} variants={len(ADV_VARIANTS)} "
          f"conditions={len(cond_names)} ({total} gate evals)")
    print(f"[gateadv] writing -> {out_path}")

    # condition -> Counter over gate decisions
    gate_by_cond: dict[str, Counter] = {c: Counter() for c in cond_names}
    # condition -> Counter over correctness of any downstream answer
    harm_by_cond: dict[str, Counter] = {c: Counter() for c in cond_names}

    with open(out_path, "w", encoding="utf-8") as out:
        for vi, v in enumerate(ADV_VARIANTS):
            generate_variant("workspace", v)   # writes taxas.txt for this variant
            gt = ground_truth(v)
            task = build_task(v)
            conds = conditions_for(v)
            for cname in cond_names:
                ctx = build_context(v, conds[cname])
                res = run_gate_and_maybe_compute(client, ctx, task, gt, "workspace")
                res.update({"variant": v, "variant_idx": vi, "condition": cname,
                            "ground_truth": gt, "expected_pass": EXPECTED_PASS[cname],
                            "model": cfg.model})
                gate_by_cond[cname][res["gate"]] += 1
                # downstream harm classification
                if res["gate"] == "FAIL":
                    harm = "ABSTAINED"
                elif res["final_correct"]:
                    harm = "PASS_CORRECT"   # proceeded and got it right
                else:
                    harm = "PASS_WRONG"     # false-pass that produced a wrong number
                res["harm"] = harm
                harm_by_cond[cname][harm] += 1
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                out.flush()
                flag = ""
                if cname != "complete" and res["gate"] != "FAIL":
                    flag = "  <-- FALSE-PASS"
                if cname == "complete" and res["gate"] == "FAIL":
                    flag = "  <-- over-paranoia"
                print(f"  v{vi} [{cname:10}] gate={res['gate']:7} harm={harm:12}"
                      f" final={res['final_value']}{flag}")

    # --- report ---
    n = len(ADV_VARIANTS)
    print("\n" + "=" * 76)
    print("GATE DECISION BY CONDITION (primary metric)")
    print("=" * 76)
    print(f"{'condition':12}{'should':8}{'PASS':>6}{'FAIL':>6}{'UNKNOWN':>9}   verdict")
    for cname in cond_names:
        gc = gate_by_cond[cname]
        should = "PASS" if EXPECTED_PASS[cname] else "FAIL"
        if EXPECTED_PASS[cname]:
            # complete: want PASS; FAIL = over-paranoia
            bad = gc["FAIL"]
            verdict = "OK" if bad == 0 else f"{bad}/{n} over-paranoid"
        else:
            # drop_*: want FAIL; PASS/UNKNOWN = FALSE-PASS (the SPOF)
            bad = gc["PASS"] + gc["UNKNOWN"]
            verdict = "OK (caught all)" if bad == 0 else f"{bad}/{n} FALSE-PASS"
        print(f"{cname:12}{should:8}{gc['PASS']:>6}{gc['FAIL']:>6}{gc['UNKNOWN']:>9}   {verdict}")

    print("\n" + "=" * 76)
    print("DOWNSTREAM HARM (secondary — partly masked by formulaic data)")
    print("=" * 76)
    for cname in cond_names:
        hc = harm_by_cond[cname]
        parts = " ".join(f"{k}={v}" for k, v in sorted(hc.items()))
        print(f"  {cname:10}: {parts}")

    # --- the SPOF number ---
    false_pass = sum(gate_by_cond[c]["PASS"] + gate_by_cond[c]["UNKNOWN"]
                     for c in cond_names if not EXPECTED_PASS[c])
    gap_total = sum(n for c in cond_names if not EXPECTED_PASS[c])
    over_paranoia = sum(gate_by_cond[c]["FAIL"] for c in cond_names if EXPECTED_PASS[c])
    complete_total = sum(n for c in cond_names if EXPECTED_PASS[c])
    print("\n" + "=" * 76)
    print("SPOF SUMMARY")
    print("=" * 76)
    print(f"  Gate FALSE-PASS rate (missed a real gap): {false_pass}/{gap_total}")
    print(f"  Gate over-paranoia  (failed on complete): {over_paranoia}/{complete_total}")
    print(f"\n[gateadv] raw -> {out_path}")


if __name__ == "__main__":
    main()
