"""The fix: explicit-interpretation declaration.

proto_gate_decl found the residual SPOF is not translation accuracy but SILENT
ambiguity resolution: "entre 200 e 250" was read as {201..249} (strictly between)
without flagging that other readings exist. The deterministic gate then ran
perfectly on a possibly-wrong premise.

Fix (same "make the belief explicit" move as belief-gate, one level up): the
declaration emits not just the set but
  - an `interpretation` string verbalizing the boundary reading, and
  - an `ambiguous` boolean: True if the phrasing admits more than one reading.

Prediction:
  - Precise phrasings: ambiguous=False, declaration unchanged from decl v1.
  - Ambiguous phrasings ("entre"): ambiguous=True, surfaced for confirmation
    instead of silently resolved.

We score: (a) declared-set accuracy (same as before), and (b) ambiguity
flagging — does the model now mark the genuinely-ambiguous case?

Run:
  python -m bench.proto_gate_decl2
"""
import json
import os
import re
import time

from . import config
from .client import ORClient
from .pricing import cost_usd
from .repl import extract_code_blocks, run_code
from .proto_gate_decl import PHRASINGS, INTENDED_B, build_task, summarize_set


DECLARE_PROMPT = """Tarefa: {task}

NAO calcule nada. DECLARE a intencao da tarefa como codigo Python. Para CADA loja,
emita o conjunto de IDs E uma declaracao explicita de como voce interpretou os
limites do intervalo. Use EXATAMENTE este formato:

```python
required_A = set(range(<inicio_A>, <fim_A>))
required_B = set(range(<inicio_B>, <fim_B>))
rate_A = <float>
rate_B = <float>
# interpretacao explicita dos limites (uma frase por loja):
interpretation_A = "li '<trecho>' como <inclusivo/exclusivo nos extremos>, ou seja IDs X a Y"
interpretation_B = "..."
# True se a frase admite mais de uma leitura razoavel dos limites, senao False:
ambiguous_A = <True/False>
ambiguous_B = <True/False>
```

Se um limite for ambiguo (ex: 'entre X e Y' pode incluir ou excluir os extremos),
marque ambiguous=True e diga na interpretacao qual leitura voce adotou. Escreva
APENAS o bloco de codigo."""


_SAFE = {"set": set, "range": range, "frozenset": frozenset, "True": True, "False": False}


def extract_decl(code: str) -> dict:
    ns: dict = {}
    try:
        exec(code, dict(_SAFE), ns)
    except Exception as e:
        return {"err": f"exec_error: {e}"}
    out = {"err": ""}
    for k in ("required_A", "required_B"):
        v = ns.get(k)
        out[k] = set(v) if v is not None else None
    for k in ("interpretation_A", "interpretation_B", "ambiguous_A", "ambiguous_B"):
        out[k] = ns.get(k)
    return out


def run_one(client: ORClient, prompt: str) -> dict:
    r = client.chat([{"role": "user", "content": prompt}])
    return {"output": r.content, "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens, "elapsed_s": r.elapsed_s}


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"gatedecl2_{run_id}.jsonl")
    print(f"[gatedecl2] model={cfg.model} phrasings={len(PHRASINGS)} (explicit-interpretation fix)")
    print(f"[gatedecl2] writing -> {out_path}\n")

    correct_A = 0
    amb_flagged_correct = 0   # ambiguous phrasing correctly marked ambiguous
    amb_false_positive = 0    # precise phrasing wrongly marked ambiguous
    n_amb = sum(1 for *_, a in PHRASINGS if a)
    n_precise = len(PHRASINGS) - n_amb

    with open(out_path, "w", encoding="utf-8") as out:
        for key, phrasing, intended_A, is_ambiguous in PHRASINGS:
            task = build_task(phrasing)
            d = run_one(client, DECLARE_PROMPT.format(task=task))
            blocks = extract_code_blocks(d["output"])
            code = blocks[0] if blocks else d["output"]
            dec = extract_decl(code)

            decl_A = dec.get("required_A")
            a_match = decl_A == intended_A
            model_says_amb = bool(dec.get("ambiguous_A"))
            if a_match:
                correct_A += 1
            if is_ambiguous and model_says_amb:
                amb_flagged_correct += 1
            if (not is_ambiguous) and model_says_amb:
                amb_false_positive += 1

            res = {
                "key": key, "phrasing": phrasing, "intended_ambiguous": is_ambiguous,
                "intended_A": summarize_set(intended_A),
                "declared_A": summarize_set(decl_A),
                "a_match": a_match,
                "model_ambiguous_A": model_says_amb,
                "interpretation_A": dec.get("interpretation_A"),
                "exec_err": dec.get("err"),
                "prompt_tokens": d["prompt_tokens"], "completion_tokens": d["completion_tokens"],
                "elapsed_s": d["elapsed_s"],
                "cost_usd": cost_usd(client.model, d["prompt_tokens"], d["completion_tokens"]),
                "model": cfg.model,
            }
            out.write(json.dumps(res, ensure_ascii=False) + "\n")
            out.flush()
            amb_mark = ""
            if is_ambiguous:
                amb_mark = "  AMB→flagged" if model_says_amb else "  AMB→MISSED"
            elif model_says_amb:
                amb_mark = "  (false-flag)"
            print(f"  {'OK' if a_match else 'XX'} {key:11} "
                  f"declared={summarize_set(decl_A):20} amb={str(model_says_amb):5}{amb_mark}")
            if dec.get("interpretation_A"):
                print(f"       \"{str(dec.get('interpretation_A'))[:90]}\"")

    print("\n" + "=" * 74)
    print("EXPLICIT-INTERPRETATION FIX — results")
    print("=" * 74)
    print(f"  Declared-set accuracy:        {correct_A}/{len(PHRASINGS)}  (v1 was 7/8)")
    print(f"  Ambiguous phrasing flagged:   {amb_flagged_correct}/{n_amb}  (v1 was 0/{n_amb})")
    print(f"  False-flag on precise phrasing: {amb_false_positive}/{n_precise}  (lower is better)")
    print("\nVerdict:")
    if amb_flagged_correct == n_amb and amb_false_positive == 0:
        print("  Fix works: ambiguity now surfaced, precise cases unchanged.")
    elif amb_flagged_correct == n_amb:
        print(f"  Ambiguity surfaced, but {amb_false_positive} precise case(s) over-flagged"
              " (model too cautious).")
    else:
        print(f"  Ambiguity still missed ({n_amb - amb_flagged_correct}/{n_amb}). The flag"
              " prompt is not enough.")
    print(f"\n[gatedecl2] raw -> {out_path}")


if __name__ == "__main__":
    main()
