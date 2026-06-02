"""Adversarial declaration test — the REPL-gate's residual SPOF.

The REPL-gate moved completeness from judgment (hard) to declaration + set
difference. The set difference is bulletproof. But the LLM still does ONE thing:
translate the task's natural language into `required = set(range(...))`. If that
translation is wrong (off-by-one on "inclusive", misreading "até"/"entre"/
half-open), the whole deterministic chain is built on a wrong premise — the gate
then correctly computes against the WRONG required set.

We never stress-tested that. The 20/20 used one unambiguous phrasing. This probes
boundary-ambiguous phrasings and measures DECLARATION ACCURACY: does the set the
LLM declared match the set the phrasing intends?

Method: ask only for the declaration, execute the emitted code in a sandbox,
extract `required_A`, compare to the intended set. No context, no gate — we are
auditing the single remaining LLM step.

Phrasings (store A; intended set in comments). Store B is fixed as an explicit
"inclusive" control to confirm the model isn't randomly off everywhere.

Run:
  python -m bench.proto_gate_decl
"""
import json
import os
import re
import time
from collections import Counter

from . import config
from .client import ORClient
from .pricing import cost_usd
from .repl import extract_code_blocks, run_code


# Each: (key, A-phrasing, intended_A_set, is_genuinely_ambiguous)
# Store B is always "de 400 a 450 (inclusive)" -> {400..450}, a fixed control.
PHRASINGS = [
    ("clear_incl",  "com ID de 200 a 250 (inclusive)",        set(range(200, 251)), False),
    ("bare",        "com ID de 200 a 250",                    set(range(200, 251)), False),
    ("entre",       "com ID entre 200 e 250",                 set(range(200, 251)), True),
    ("ate",         "com IDs de 200 até 250",                 set(range(200, 251)), False),
    ("half_open",   "com IDs no intervalo [200, 250)",        set(range(200, 250)), False),
    ("count",       "os 51 IDs a partir do ID 200",           set(range(200, 251)), False),
    ("excl_250",    "com IDs de 200 a 250, mas excluindo 250", set(range(200, 250)), False),
    ("first_n",     "os primeiros 50 IDs começando em 200",   set(range(200, 250)), False),
]

INTENDED_B = set(range(400, 451))


def build_task(a_phrasing: str) -> str:
    return (
        f"Calcule o imposto total sobre as transacoes da Loja A {a_phrasing} "
        f"(taxa 8%) somado ao imposto sobre as transacoes da Loja B de 400 a 450 "
        f"(inclusive) (taxa 12%)."
    )


DECLARE_PROMPT = """Tarefa: {task}

NAO calcule nada. Apenas DECLARE a intencao da tarefa como codigo Python, com
EXATAMENTE estas variaveis:

    required_A = set(range(<inicio_A>, <fim_A>))   # os IDs da Loja A que a tarefa exige
    required_B = set(range(<inicio_B>, <fim_B>))   # os IDs da Loja B que a tarefa exige
    rate_A = <aliquota_A_float>
    rate_B = <aliquota_B_float>

Traduza as faixas de ID exatamente como a tarefa as descreve. Preste atencao a
limites (inclusive, exclusive, 'ate', 'entre', intervalo aberto/fechado,
contagens). Escreva APENAS o bloco de codigo."""


def extract_declared_sets(code: str) -> tuple[set | None, set | None, str]:
    """Execute the declaration in a sandbox and pull out required_A / required_B."""
    ns: dict = {}
    try:
        # only allow set/range builtins; declaration shouldn't need more
        exec(code, {"set": set, "range": range, "frozenset": frozenset}, ns)
    except Exception as e:
        return None, None, f"exec_error: {e}"
    a = ns.get("required_A")
    b = ns.get("required_B")
    a = set(a) if a is not None else None
    b = set(b) if b is not None else None
    return a, b, ""


def summarize_set(s: set | None) -> str:
    if s is None:
        return "None"
    if not s:
        return "empty"
    lo, hi = min(s), max(s)
    contiguous = (len(s) == hi - lo + 1)
    return f"[{lo}..{hi}] n={len(s)}{'' if contiguous else ' (non-contiguous)'}"


def run_one(client: ORClient, prompt: str) -> dict:
    r = client.chat([{"role": "user", "content": prompt}])
    return {"output": r.content, "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens, "elapsed_s": r.elapsed_s}


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"gatedecl_{run_id}.jsonl")
    print(f"[gatedecl] model={cfg.model} phrasings={len(PHRASINGS)}")
    print(f"[gatedecl] writing -> {out_path}")
    print(f"[gatedecl] auditing the single remaining LLM step: language -> required set\n")

    correct_A = 0
    b_control_correct = 0
    ambiguous_flagged = 0
    rows = []

    with open(out_path, "w", encoding="utf-8") as out:
        for key, phrasing, intended_A, ambiguous in PHRASINGS:
            task = build_task(phrasing)
            d = run_one(client, DECLARE_PROMPT.format(task=task))
            blocks = extract_code_blocks(d["output"])
            code = blocks[0] if blocks else d["output"]
            decl_A, decl_B, err = extract_declared_sets(code)

            a_match = decl_A == intended_A
            b_match = decl_B == INTENDED_B
            if a_match:
                correct_A += 1
            if b_match:
                b_control_correct += 1
            # did the model flag ambiguity in its text (only meaningful for ambiguous ones)?
            flagged = bool(re.search(r"ambig|inclusiv|exclus|assum|interpret|n[ãa]o.*claro",
                                     d["output"], re.IGNORECASE))
            if ambiguous and flagged:
                ambiguous_flagged += 1

            res = {
                "key": key, "phrasing": phrasing, "ambiguous": ambiguous,
                "intended_A": summarize_set(intended_A),
                "declared_A": summarize_set(decl_A),
                "declared_B": summarize_set(decl_B),
                "a_match": a_match, "b_control_match": b_match,
                "flagged_ambiguity": flagged, "exec_err": err,
                "declare_code": code[:200],
                "prompt_tokens": d["prompt_tokens"], "completion_tokens": d["completion_tokens"],
                "elapsed_s": d["elapsed_s"],
                "cost_usd": cost_usd(client.model, d["prompt_tokens"], d["completion_tokens"]),
                "model": cfg.model,
            }
            rows.append(res)
            out.write(json.dumps(res, ensure_ascii=False) + "\n")
            out.flush()
            mark = "OK " if a_match else "XX "
            amb = " [ambiguous]" if ambiguous else ""
            print(f"  {mark}{key:11} declared_A={summarize_set(decl_A):28} "
                  f"intended={summarize_set(intended_A):16}{amb}")

    n = len(PHRASINGS)
    n_amb = sum(1 for *_, a in PHRASINGS if a)
    print("\n" + "=" * 74)
    print("DECLARATION ACCURACY (the residual SPOF)")
    print("=" * 74)
    print(f"  Store A declared-set correct: {correct_A}/{n}")
    print(f"  Store B control correct:      {b_control_correct}/{n}  (sanity: should be ~{n})")
    print(f"  Ambiguous phrasings flagged:  {ambiguous_flagged}/{n_amb}")
    print("\nWrong declarations (these would silently build the gate on a wrong premise):")
    any_wrong = False
    for r in rows:
        if not r["a_match"]:
            any_wrong = True
            print(f"  - {r['key']:11} '{r['phrasing']}'")
            print(f"      declared {r['declared_A']}  vs intended {r['intended_A']}")
    if not any_wrong:
        print("  (none — declaration step held)")
    print(f"\n[gatedecl] raw -> {out_path}")


if __name__ == "__main__":
    main()
