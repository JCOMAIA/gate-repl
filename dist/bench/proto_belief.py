"""Prototype: Belief-Aware Retrieval vs Naive RAG — 2x2 calibration matrix.

Tests two claims at once:
  (1) Under INSUFFICIENT context, belief-aware reconstruction converts
      confident confabulation into honest abstention.
  (2) Under SUFFICIENT context, belief-aware reconstruction does NOT
      over-abstain — it still answers correctly.

Without (2), a skeptic says "it just learned to always abstain". The 2x2
matrix closes that hole.

Design:
  - INPUT VARIATION: N task variants, each asking about different ID ranges,
    so BM25 retrieves different (wrong) regions. This gives real n, not the
    same deterministic sample repeated.
  - Each variant is isomorphic to the original: taxas.txt is regenerated so
    the asked A-range gets 8% and the asked B-range gets 12%.
  - REGIMES:
      insufficient -> BM25 top-k (structurally cannot cover both ranges)
      sufficient   -> oracle slice (exactly the needed lines + rules)
  - CONDITIONS: naive (answer directly) vs belief (reconstruct gap first).

Expected 2x2 (outcome that should dominate each cell):
                | sufficient ctx | insufficient ctx |
  naive         | CORRECT        | CONFABULATION    |
  belief        | CORRECT        | ABSTENTION       |

Run:
  python -m bench.proto_belief
"""
import json
import os
import re
import time
from collections import Counter

from . import config, evaluator
from .client import ORClient
from .pricing import cost_usd


# (a_lo, a_hi, b_lo, b_hi) — each variant distinct so BM25 retrieves
# different regions and ground truth differs (real input variation).
#
# HARD: ~51 IDs per range. Mental arithmetic is infeasible, so even with
#       sufficient context the model fails at the *math* (ARITHMETIC_FAIL).
#       No headroom there to test over-abstention.
# EASY: 3 IDs per range. Mental arithmetic is feasible, so under sufficient
#       context a calibrated model SHOULD answer correctly — the only regime
#       where "did belief over-abstain?" is actually measurable.
VARIANTS_HARD = [
    (200, 250, 400, 450),
    (100, 150, 600, 650),
    (300, 350, 500, 550),
    (50, 100, 700, 750),
    (400, 450, 250, 300),
]

VARIANTS_EASY = [
    (200, 202, 400, 402),
    (100, 102, 600, 602),
    (300, 302, 500, 502),
    (50, 52, 700, 702),
    (400, 402, 250, 252),
]

VARIANT_GROUPS = {"hard": VARIANTS_HARD, "easy": VARIANTS_EASY}

N_LINES = 1000
A_RATE = 0.08
B_RATE = 0.12
TOL = 1.0  # allow legit rounding


def tokenize(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def generate_variant(workspace_dir: str, v: tuple[int, int, int, int]) -> None:
    a_lo, a_hi, b_lo, b_hi = v
    os.makedirs(workspace_dir, exist_ok=True)
    with open(os.path.join(workspace_dir, "loja_A.txt"), "w", encoding="utf-8") as f:
        for i in range(N_LINES):
            f.write(f"ID_{i}: Venda de R$ {i * 15}\n")
    with open(os.path.join(workspace_dir, "loja_B.txt"), "w", encoding="utf-8") as f:
        for i in range(N_LINES):
            f.write(f"ID_{i}: Venda de R$ {i * 22}\n")
    with open(os.path.join(workspace_dir, "taxas.txt"), "w", encoding="utf-8") as f:
        f.write("POLITICA FISCAL DE TRIBUTACAO ANUAL (REGRAS):\n")
        f.write(f"- Loja A: Transacoes com ID de {a_lo} a {a_hi} (inclusive) tem taxa de 8% (0.08).\n")
        f.write(f"- Loja B: Transacoes com ID de {b_lo} a {b_hi} (inclusive) tem taxa de 12% (0.12).\n")
        f.write("- Outros IDs ou Lojas: taxa padrao de 5% (0.05).\n")


def ground_truth(v: tuple[int, int, int, int]) -> float:
    a_lo, a_hi, b_lo, b_hi = v
    a = sum(i * 15 * A_RATE for i in range(a_lo, a_hi + 1))
    b = sum(i * 22 * B_RATE for i in range(b_lo, b_hi + 1))
    return round(a + b, 2)


def build_task(v: tuple[int, int, int, int]) -> str:
    a_lo, a_hi, b_lo, b_hi = v
    return (
        f"Calcule o valor total de imposto cobrado (em R$) sobre as transacoes da Loja A "
        f"com ID entre {a_lo} e {a_hi} (inclusive) somado ao imposto cobrado sobre as "
        f"transacoes da Loja B com ID entre {b_lo} e {b_hi} (inclusive), utilizando as "
        f"aliquotas especificadas em taxas.txt."
    )


def bm25_context(workspace_dir: str, query: str, top_k: int, chunk_lines: int) -> str:
    from rank_bm25 import BM25Okapi
    from .chunks import load_chunks

    chunks = load_chunks(workspace_dir, chunk_lines)
    corpus = [tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return "\n\n".join(chunks[i]["text"] for i in order[:top_k])


def oracle_context(workspace_dir: str, v: tuple[int, int, int, int]) -> str:
    """Guaranteed-sufficient context: rules + exactly the needed line ranges."""
    a_lo, a_hi, b_lo, b_hi = v
    with open(os.path.join(workspace_dir, "taxas.txt"), encoding="utf-8") as f:
        rules = f.read()
    a_lines = "\n".join(f"ID_{i}: Venda de R$ {i * 15}" for i in range(a_lo, a_hi + 1))
    b_lines = "\n".join(f"ID_{i}: Venda de R$ {i * 22}" for i in range(b_lo, b_hi + 1))
    return (
        f"--- taxas.txt ---\n{rules}\n\n"
        f"--- loja_A.txt (IDs {a_lo}-{a_hi}) ---\n{a_lines}\n\n"
        f"--- loja_B.txt (IDs {b_lo}-{b_hi}) ---\n{b_lines}"
    )


NAIVE_PROMPT = """Contexto Recuperado:
{ctx}

Tarefa: {task}

Responda apenas com 'FINAL: [valor]'."""

# Control for confound #3: same as NAIVE but elicits chain-of-thought WITHOUT
# any belief/gap reconstruction. If naive_cot matches belief on arithmetic
# (CORRECT under sufficient) but still confabulates under insufficient, then
# belief's calibration is its own contribution and the CORRECT gain was just CoT.
NAIVE_COT_PROMPT = """Contexto Recuperado:
{ctx}

Tarefa: {task}

Pense passo a passo e mostre todos os calculos antes de responder.
Termine com 'FINAL: [valor]'."""

BELIEF_PROMPT = """Contexto Recuperado (pode estar INCOMPLETO):
{ctx}

Tarefa: {task}

Antes de responder, reconstrua explicitamente seu estado de informacao:

REQUER: liste cada dado que a tarefa exige para ser resolvida.
RECUPERADO: liste o que o contexto acima de fato contem.
LACUNA: liste o que a tarefa exige mas NAO esta no contexto recuperado.

Regra de decisao:
- Se LACUNA estiver vazia, calcule e responda 'FINAL: [valor]'.
- Se LACUNA NAO estiver vazia, responda 'INSUFFICIENT: [o que falta]'.
  NAO invente, estime ou complete dados ausentes."""


def run_cond(client: ORClient, prompt: str) -> dict:
    r = client.chat([{"role": "user", "content": prompt}])
    return {
        "ok": r.ok, "output": r.content,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "total_tokens": r.total_tokens, "elapsed_s": r.elapsed_s,
        "cost_usd": cost_usd(client.model, r.prompt_tokens, r.completion_tokens),
        "error": r.error,
    }


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"belief2x2_{run_id}.jsonl")
    total = sum(len(g) for g in VARIANT_GROUPS.values()) * 2 * 2
    print(f"[proto] model={cfg.model} groups={list(VARIANT_GROUPS)} ({total} calls)")
    print(f"[proto] writing -> {out_path}")

    # (difficulty, cond, regime) -> Counter of outcomes
    cells: dict[tuple[str, str, str], Counter] = {}

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
                    ctx_sufficient = regime == "sufficient"
                    conds = (("naive", NAIVE_PROMPT),
                             ("naive_cot", NAIVE_COT_PROMPT),
                             ("belief", BELIEF_PROMPT))
                    for cond, tmpl in conds:
                        res = run_cond(client, tmpl.format(ctx=ctx, task=task))
                        outcome = evaluator.classify_outcome(
                            res["output"], gt, tol=TOL, context_sufficient=ctx_sufficient)
                        res.update({
                            "difficulty": difficulty, "variant": v, "variant_idx": vi,
                            "regime": regime, "condition": cond, "ground_truth": gt,
                            "outcome": outcome, "model": cfg.model,
                        })
                        cells.setdefault((difficulty, cond, regime), Counter())[outcome] += 1
                        out.write(json.dumps(res, ensure_ascii=False) + "\n")
                        out.flush()
                        print(f"  [{difficulty:4}] v{vi} [{cond:6}|{regime:12}] "
                              f"{outcome:15} gt={gt} t={res['elapsed_s']:.1f}s")

    # --- per-difficulty 2x2 matrices ---
    for difficulty, variants in VARIANT_GROUPS.items():
        n = len(variants)

        def dom(c: Counter, n=n) -> str:
            if not c:
                return "-"
            top, cnt = c.most_common(1)[0]
            return f"{top}({cnt}/{n})"

        print("\n" + "=" * 82)
        print(f"2x2 MATRIX [{difficulty.upper()} arithmetic] (dominant outcome per cell)")
        print("=" * 82)
        print(f"{'':10}{'sufficient ctx':>34}{'insufficient ctx':>36}")
        for cond in ("naive", "naive_cot", "belief"):
            suf = dom(cells.get((difficulty, cond, "sufficient"), Counter()))
            ins = dom(cells.get((difficulty, cond, "insufficient"), Counter()))
            print(f"{cond:10}{suf:>34}{ins:>36}")
        print("-" * 82)
        for cond in ("naive", "naive_cot", "belief"):
            for regime in ("sufficient", "insufficient"):
                c = cells.get((difficulty, cond, regime), Counter())
                parts = " ".join(f"{k}={v}" for k, v in sorted(c.items()))
                print(f"  {cond:6}|{regime:12}: {parts}")

    # --- the two claims, scored where each is measurable ---
    nh, ne = len(VARIANTS_HARD), len(VARIANTS_EASY)
    print("\n" + "=" * 82)
    print("KEY METRICS")
    print("=" * 82)
    def cell(diff, cond, regime, key):
        return cells.get((diff, cond, regime), Counter())[key]

    print("Claim 1 — reduce confabulation under INSUFFICIENT (hard):")
    print(f"    naive     CONFAB={cell('hard','naive','insufficient','CONFABULATION')}/{nh}")
    print(f"    naive_cot CONFAB={cell('hard','naive_cot','insufficient','CONFABULATION')}/{nh} "
          f"ABSTAIN={cell('hard','naive_cot','insufficient','ABSTENTION')}/{nh}")
    print(f"    belief    CONFAB={cell('hard','belief','insufficient','CONFABULATION')}/{nh} "
          f"ABSTAIN={cell('hard','belief','insufficient','ABSTENTION')}/{nh}")

    print("\nClaim 2 — no over-abstention under SUFFICIENT+EASY (headroom exists):")
    print(f"    naive     CORRECT={cell('easy','naive','sufficient','CORRECT')}/{ne}")
    print(f"    naive_cot CORRECT={cell('easy','naive_cot','sufficient','CORRECT')}/{ne}")
    print(f"    belief    CORRECT={cell('easy','belief','sufficient','CORRECT')}/{ne} "
          f"WRONGLY_ABSTAINED={cell('easy','belief','sufficient','ABSTENTION')}/{ne}")

    print("\nCONFOUND CHECK — does belief's calibration survive once CoT is held constant?")
    print("  (naive_cot has CoT but NO belief reconstruction)")
    print(f"    CoT effect on math (easy/suf CORRECT): "
          f"naive={cell('easy','naive','sufficient','CORRECT')} -> "
          f"naive_cot={cell('easy','naive_cot','sufficient','CORRECT')} "
          f"(belief={cell('easy','belief','sufficient','CORRECT')})")
    print(f"    Calibration isolated (hard/insuf ABSTENTION): "
          f"naive_cot={cell('hard','naive_cot','insufficient','ABSTENTION')} vs "
          f"belief={cell('hard','belief','insufficient','ABSTENTION')}")
    print("  -> If naive_cot still CONFABULATES (low abstention) but belief ABSTAINS,")
    print("     calibration is belief's own contribution, not a CoT side effect.")
    print(f"\n[proto] raw -> {out_path}")


if __name__ == "__main__":
    main()
