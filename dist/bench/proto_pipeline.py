"""Payoff experiment: the SEQUENTIAL belief-gate -> REPL pipeline.

The double dissociation (proto_belief) showed:
  - CoT fixes math but not calibration
  - belief fixes calibration but not math
  - fusing both into one prompt degrades both

This tests the architectural conclusion: decouple the two stages.

  Stage 1 — BELIEF GATE: reconstruct REQUER/RECUPERADO/LACUNA on the retrieved
            context. If LACUNA is non-empty -> ABSTAIN (no computation attempted).
  Stage 2 — REPL COMPUTE: only if the gate passes, the model writes Python that
            parses the SAME context and computes the sum. Execution is
            deterministic, so arithmetic is correct by construction (not by
            mental math).

Prediction (pre-registered):
  pipeline gets BOTH 5/5 calibration (abstain under insufficient) AND 5/5 math
  (correct under sufficient) — INCLUDING hard/sufficient, where belief-alone and
  naive both scored 0/5 because mental arithmetic over ~51 IDs is infeasible.

Comparison arms reuse proto_belief outcomes; here we add the `pipeline` arm and
report it against the same 2x2 grid.

Run:
  python -m bench.proto_pipeline
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
from .proto_belief import (
    VARIANT_GROUPS, VARIANTS_HARD, VARIANTS_EASY, TOL,
    generate_variant, ground_truth, build_task,
    oracle_context, bm25_context,
)


GATE_PROMPT = """Contexto Recuperado (pode estar INCOMPLETO):
{ctx}

Tarefa: {task}

NAO calcule ainda. Apenas avalie se o contexto contem TODOS os dados necessarios.

REQUER: liste cada dado que a tarefa exige.
RECUPERADO: liste o que o contexto acima de fato contem.
LACUNA: liste o que a tarefa exige mas NAO esta no contexto.

Termine com exatamente uma linha:
- 'GATE: PASS'  se a LACUNA estiver vazia.
- 'GATE: FAIL'  se faltar qualquer dado."""

COMPUTE_PROMPT = """Voce tem uma variavel Python chamada `context` (string) ja
carregada no ambiente, contendo os dados necessarios:

--- inicio do conteudo de context ---
{ctx}
--- fim ---

Tarefa: {task}

Escreva codigo Python que processa a string `context` (faca parse com regex,
some os valores, aplique as aliquotas) e imprime o resultado com:
    print(f'FINAL: {{resultado}}')
Escreva APENAS o bloco de codigo Python."""

_GATE = re.compile(r"GATE\s*:\s*(PASS|FAIL)", re.IGNORECASE)


def run_one(client: ORClient, prompt: str) -> dict:
    r = client.chat([{"role": "user", "content": prompt}])
    return {
        "ok": r.ok, "output": r.content,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "total_tokens": r.total_tokens, "elapsed_s": r.elapsed_s,
        "cost_usd": cost_usd(client.model, r.prompt_tokens, r.completion_tokens),
        "error": r.error,
    }


def gate_decision(gate_output: str) -> str:
    """Return 'PASS', 'FAIL', or 'UNKNOWN' from the gate's text."""
    m = _GATE.search(gate_output)
    if m:
        return m.group(1).upper()
    # fallback: a non-empty LACUNA means FAIL
    if evaluator._lacuna_signals_gap(gate_output):
        return "FAIL"
    return "UNKNOWN"


def run_pipeline(client: ORClient, ctx: str, task: str, gt: float,
                 workspace_dir: str) -> dict:
    """Two-stage: gate, then (if pass) REPL compute. Returns a result dict
    with a unified `outcome` and the per-stage trace."""
    # --- Stage 1: belief gate ---
    g = run_one(client, GATE_PROMPT.format(ctx=ctx, task=task))
    decision = gate_decision(g["output"])
    prompt_tokens = g["prompt_tokens"]
    completion_tokens = g["completion_tokens"]
    elapsed = g["elapsed_s"]

    if decision == "FAIL":
        return {
            "outcome": "ABSTENTION", "gate": "FAIL", "stages": 1,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens, "elapsed_s": elapsed,
            "cost_usd": cost_usd(client.model, prompt_tokens, completion_tokens),
            "gate_output": g["output"][:400], "compute_output": "", "parsed_value": None,
        }

    # --- Stage 2: REPL compute (gate PASS or UNKNOWN-treated-as-pass) ---
    c = run_one(client, COMPUTE_PROMPT.format(ctx=ctx, task=task))
    prompt_tokens += c["prompt_tokens"]
    completion_tokens += c["completion_tokens"]
    elapsed += c["elapsed_s"]

    blocks = extract_code_blocks(c["output"])
    code = blocks[0] if blocks else c["output"]
    repl_out = run_code(code, workspace_dir, glb={"context": ctx})
    parsed = evaluator.extract_final_number(repl_out)
    # outcome: CORRECT if REPL produced the right number, else a compute failure
    if evaluator.matches(parsed, gt, tol=TOL):
        outcome = "CORRECT"
    elif parsed is not None:
        outcome = "REPL_WRONG"   # gate passed but code/computation was wrong
    else:
        outcome = "REPL_NO_OUTPUT"

    return {
        "outcome": outcome, "gate": decision, "stages": 2,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens, "elapsed_s": elapsed,
        "cost_usd": cost_usd(client.model, prompt_tokens, completion_tokens),
        "gate_output": g["output"][:300], "compute_output": repl_out[:300],
        "parsed_value": parsed,
    }


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"pipeline_{run_id}.jsonl")
    total = sum(len(g) for g in VARIANT_GROUPS.values()) * 2
    print(f"[pipeline] model={cfg.model} ({total} pipeline runs, 2 stages each)")
    print(f"[pipeline] writing -> {out_path}")

    cells: dict[tuple[str, str], Counter] = {}

    with open(out_path, "w", encoding="utf-8") as out:
        for difficulty, variants in VARIANT_GROUPS.items():
            for vi, v in enumerate(variants):
                generate_variant(cfg.workspace_dir, v)
                gt = ground_truth(v)
                task = build_task(v)
                a_lo, a_hi, b_lo, b_hi = v
                query = (f"loja A transacoes ID {a_lo} a {a_hi} loja B {b_lo} a {b_hi} "
                         f"aliquotas taxas imposto")
                contexts = {
                    "sufficient": oracle_context(cfg.workspace_dir, v),
                    "insufficient": bm25_context(cfg.workspace_dir, query,
                                                 cfg.rag_top_k, cfg.rag_chunk_lines),
                }
                for regime, ctx in contexts.items():
                    res = run_pipeline(client, ctx, task, gt, cfg.workspace_dir)
                    res.update({
                        "difficulty": difficulty, "variant": v, "variant_idx": vi,
                        "regime": regime, "ground_truth": gt, "model": cfg.model,
                    })
                    cells.setdefault((difficulty, regime), Counter())[res["outcome"]] += 1
                    out.write(json.dumps(res, ensure_ascii=False) + "\n")
                    out.flush()
                    print(f"  [{difficulty:4}] v{vi} [{regime:12}] "
                          f"gate={res['gate']:4} -> {res['outcome']:14} "
                          f"parsed={res['parsed_value']} t={res['elapsed_s']:.1f}s")

    # --- report: pipeline 2x2 ---
    print("\n" + "=" * 78)
    print("PIPELINE 2x2 (belief gate -> REPL compute)")
    print("=" * 78)
    for difficulty in VARIANT_GROUPS:
        n = len(VARIANT_GROUPS[difficulty])
        suf = cells.get((difficulty, "sufficient"), Counter())
        ins = cells.get((difficulty, "insufficient"), Counter())
        sfmt = " ".join(f"{k}={v}" for k, v in sorted(suf.items())) or "-"
        ifmt = " ".join(f"{k}={v}" for k, v in sorted(ins.items())) or "-"
        print(f"  [{difficulty}] sufficient  : {sfmt}")
        print(f"  [{difficulty}] insufficient: {ifmt}")

    # --- the payoff check ---
    def cell(diff, regime, key):
        return cells.get((diff, regime), Counter())[key]

    nh, ne = len(VARIANTS_HARD), len(VARIANTS_EASY)
    print("\n" + "=" * 78)
    print("PAYOFF CHECK — does the pipeline get BOTH?")
    print("=" * 78)
    print("Calibration (insufficient -> ABSTENTION):")
    print(f"    hard: {cell('hard','insufficient','ABSTENTION')}/{nh}   "
          f"easy: {cell('easy','insufficient','ABSTENTION')}/{ne}")
    print("Math (sufficient -> CORRECT, via REPL):")
    print(f"    hard: {cell('hard','sufficient','CORRECT')}/{nh}   "
          f"easy: {cell('easy','sufficient','CORRECT')}/{ne}")
    print("\nKey contrast vs single-prompt arms (from proto_belief):")
    print("    hard/sufficient: belief-alone=0/5, naive=0/5  ->  pipeline target=5/5")
    print("    (because REPL executes the sum instead of doing mental arithmetic)")
    print(f"\n[pipeline] raw -> {out_path}")


if __name__ == "__main__":
    main()
