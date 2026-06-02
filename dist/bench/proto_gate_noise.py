"""Noisy-context parsing test — the gate's other dependency.

The REPL-gate's set difference is bulletproof IF the present-set is parsed
correctly. In the clean benchmark the data was perfectly formatted
(`ID_207: ...`). Real retrieved/exported data is messy: dashes, lowercase,
spaces, inline annotations, prose. If the LLM-written parser misses a
present-but-noisy record, the gate FALSE-FAILS (reports missing data that is
actually there) — annoying, not dangerous, but a real reliability gap.

This tests the realistic deployment: the MODEL writes the extraction code (as
the SKILL instructs, "adapt the pattern to your data"), given noisy context.
We then run its code and check whether the present-set it recovered matches the
true present-set.

Conditions (required = IDs 200-210, all 11 PRESENT but in varying surface forms):
  clean        — ID_200: ...                         (baseline)
  mixed_delim  — ID_200 / ID-201 / id 202 / ID 203   (delimiter/case variation)
  annotated    — ID_200 (cancelado) / ID_201 [ok]    (inline annotations)
  prose        — "Transacao 200 no valor de R$ ..."  (no ID_ prefix at all)

Primary metric: does the model's parser recover all 11 present IDs?
  - recovered == present  → parser robust (gate would correctly PASS)
  - recovered  < present  → FALSE-FAIL (parser missed noisy records)

A separate `missing_one` row per style (ID_205 actually removed) checks the
parser still correctly flags a REAL gap amid the noise.

Run:
  python -m bench.proto_gate_noise
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


LO, HI = 200, 210
REQUIRED = set(range(LO, HI + 1))   # 11 IDs


def fmt_clean(i, v):     return f"ID_{i}: Venda de R$ {v}"
def fmt_dash(i, v):      return f"ID-{i}: Venda de R$ {v}"
def fmt_space(i, v):     return f"ID {i}: Venda de R$ {v}"
def fmt_lower(i, v):     return f"id {i} -> R$ {v}"
_ANNOTS = ["[ok]", "(revisado)", "- conferido", "(2024)", "// nota"]
def fmt_annot(i, v):     return f"ID_{i} {_ANNOTS[i % len(_ANNOTS)]}: Venda de R$ {v}"
def fmt_prose(i, v):     return f"Transacao {i} no valor de R$ {v}."


def build_context(style: str, drop: set[int]) -> str:
    """All IDs LO..HI present (minus `drop`), formatted per style.
    'mixed_delim' rotates through delimiter/case variants per line."""
    lines = []
    for i in range(LO, HI + 1):
        if i in drop:
            continue
        v = i * 15
        if style == "clean":
            lines.append(fmt_clean(i, v))
        elif style == "annotated":
            lines.append(fmt_annot(i, v))
        elif style == "prose":
            lines.append(fmt_prose(i, v))
        elif style == "mixed_delim":
            lines.append([fmt_clean, fmt_dash, fmt_space, fmt_lower][i % 4](i, v))
        else:
            lines.append(fmt_clean(i, v))
    return "\n".join(lines)


PROMPT = """Voce tem uma variavel Python `context` (string) com registros de
transacoes. O formato pode ser IRREGULAR (delimitadores variados, maiusculas/
minusculas, anotacoes, ou texto corrido).

--- inicio de context ---
{ctx}
--- fim ---

A tarefa exige os IDs de {lo} a {hi} (inclusive). Escreva codigo Python que:
1. extraia o CONJUNTO de IDs realmente presentes em `context` (seja robusto ao
   formato irregular — nem todo registro usa 'ID_<n>:'),
2. compute a lacuna = required - present, onde required = set(range({lo}, {hi}+1)),
3. imprima exatamente:
   print(f'PRESENT: {{sorted(present)}}')
   print(f'GAP: {{sorted(gap)}}')
Escreva APENAS o bloco de codigo."""


def run_one(client, prompt):
    r = client.chat([{"role": "user", "content": prompt}])
    return {"output": r.content, "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens, "elapsed_s": r.elapsed_s}


def parse_present(repl_out: str) -> set | None:
    m = re.search(r"PRESENT:\s*\[([^\]]*)\]", repl_out)
    if not m:
        return None
    nums = re.findall(r"\d+", m.group(1))
    return set(int(n) for n in nums)


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"gatenoise_{run_id}.jsonl")

    styles = ["clean", "mixed_delim", "annotated", "prose"]
    # (label, dropped set, expected present set)
    scenarios = [("full", set()), ("missing_205", {205})]
    print(f"[gatenoise] model={cfg.model} styles={styles} scenarios={[s[0] for s in scenarios]}")
    print(f"[gatenoise] writing -> {out_path}")
    print(f"[gatenoise] required = IDs {LO}-{HI} ({len(REQUIRED)} ids); model writes the parser\n")

    results = Counter()
    rows = []
    with open(out_path, "w", encoding="utf-8") as out:
        for style in styles:
            for label, drop in scenarios:
                true_present = REQUIRED - drop
                ctx = build_context(style, drop)
                d = run_one(client, PROMPT.format(ctx=ctx, lo=LO, hi=HI))
                blocks = extract_code_blocks(d["output"])
                code = blocks[0] if blocks else d["output"]
                repl_out = run_code(code, ".", glb={"context": ctx})
                recovered = parse_present(repl_out)

                if recovered is None:
                    verdict = "NO_OUTPUT"
                elif recovered == true_present:
                    verdict = "OK"
                elif recovered < true_present:
                    verdict = "FALSE_FAIL"   # missed present records
                elif recovered > true_present:
                    verdict = "OVER"          # invented/included IDs it shouldn't
                else:
                    verdict = "WRONG"
                results[verdict] += 1

                res = {
                    "style": style, "scenario": label,
                    "true_present_n": len(true_present),
                    "recovered_n": len(recovered) if recovered is not None else None,
                    "missed": sorted(true_present - recovered) if recovered else None,
                    "extra": sorted(recovered - true_present) if recovered else None,
                    "verdict": verdict,
                    "repl_output": repl_out[:160],
                    "code": code[:200],
                    "prompt_tokens": d["prompt_tokens"], "completion_tokens": d["completion_tokens"],
                    "elapsed_s": d["elapsed_s"],
                    "cost_usd": cost_usd(client.model, d["prompt_tokens"], d["completion_tokens"]),
                    "model": cfg.model,
                }
                rows.append(res)
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                out.flush()
                extra = ""
                if res["missed"]:
                    extra = f" missed={res['missed']}"
                if res["extra"]:
                    extra += f" extra={res['extra']}"
                print(f"  {verdict:11} [{style:11}|{label:11}] "
                      f"recovered {res['recovered_n']}/{len(true_present)}{extra}")

    print("\n" + "=" * 74)
    print("NOISY-PARSE ROBUSTNESS")
    print("=" * 74)
    total = sum(results.values())
    for k in ("OK", "FALSE_FAIL", "OVER", "WRONG", "NO_OUTPUT"):
        if results[k]:
            print(f"  {k:11}: {results[k]}/{total}")
    print("\nFALSE_FAIL = parser missed a present-but-noisy record (gate would")
    print("wrongly report missing data). OK = recovered the true present set despite noise.")
    print(f"\n[gatenoise] raw -> {out_path}")


if __name__ == "__main__":
    main()
