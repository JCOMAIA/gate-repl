"""Does structured declaration preserve modality where lossy compression erases it?
And — the §5 hypothesis — is the modality bounded/checkable rather than pure judgment?

Three write→recall pipelines per statement:

  lossy       — LLM compresses the turn into a short "fact to remember" (as current
                AI-memory tools do). At recall, a second LLM classifies the modality
                of the COMPRESSED fact. Tests whether compression erased modality.
  structured  — LLM emits modality as a REQUIRED field at write time
                ('MODALITY: decision|option|hypothesis'). Recall reads the field.
                Tests whether forcing a slot preserves modality.
  deterministic_check — NOT a memory method; a checker. Given the ORIGINAL text,
                a rule-based classifier keys on surface modal markers. Tests the §5
                claim: is modality bounded into checkable structure, or only judgable?
                If this rule-based pass does well, modality reduces to structured
                extraction (hypothesis TRUE); if it fails badly, modality needs real
                understanding (hypothesis FALSE).

Primary metric: UPWARD-INVERSION rate — a hedge (option/hypothesis) recalled as a
decision. The dangerous error; the analogue of belief-gate's false-complete.

Run:  python -m bench.modality.harness --n 30
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter

from .. import config
from ..client import ORClient
from ..pricing import cost_usd
from .dataset import generate, is_upward_inversion, COMMITMENT


# ----------------------------- the three pipelines -----------------------------

COMPRESS_P = """Você é um sistema de memória de agente. Comprima o turno abaixo em UM
fato curto a ser lembrado depois (máx 12 palavras). Apenas o fato, sem aspas.

Turno: {text}"""

CLASSIFY_P = """Classifique o status modal deste fato como exatamente uma palavra:
'decision' (algo decidido/comprometido), 'option' (uma possibilidade em
consideração) ou 'hypothesis' (uma crença tentativa/suposição).

Fato: {fact}
Responda só a palavra."""

STRUCT_P = """Extraia, do turno abaixo, o conteúdo E o status modal, neste formato EXATO:
FACT: <o conteúdo em até 12 palavras>
MODALITY: <decision|option|hypothesis>

Onde modality é: decision = decidido/comprometido; option = possibilidade em
consideração; hypothesis = crença tentativa/suposição.

Turno: {text}"""

_WORD = re.compile(r"\b(decision|option|hypothesis)\b", re.IGNORECASE)
_MOD = re.compile(r"MODALITY:\s*(decision|option|hypothesis)", re.IGNORECASE)
_FACT = re.compile(r"FACT:\s*(.+)", re.IGNORECASE)


def _norm(m: str | None) -> str | None:
    return m.lower() if m else None


def pipe_lossy(client, text):
    c = client.chat([{"role": "user", "content": COMPRESS_P.format(text=text)}])
    fact = c.content.strip()
    r = client.chat([{"role": "user", "content": CLASSIFY_P.format(fact=fact)}])
    m = _WORD.search(r.content)
    pt = c.prompt_tokens + r.prompt_tokens
    ct = c.completion_tokens + r.completion_tokens
    el = c.elapsed_s + r.elapsed_s
    return _norm(m.group(1) if m else None), fact[:80], pt, ct, el


def pipe_structured(client, text):
    c = client.chat([{"role": "user", "content": STRUCT_P.format(text=text)}])
    m = _MOD.search(c.content)
    fm = _FACT.search(c.content)
    fact = fm.group(1).strip() if fm else c.content[:60]
    return _norm(m.group(1) if m else None), fact[:80], c.prompt_tokens, c.completion_tokens, c.elapsed_s


# Deterministic rule-based checker on the ORIGINAL text (no LLM). The §5 probe.
DECISION_CUES = ["vamos", "decidimos", "será", "definido", "confirmado", "seguimos com"]
OPTION_CUES = ["poderíamos", "poderia", "alternativa", "talvez valha", "considerar",
               "possibilidade", "possível", "avaliando", "avaliar", "uma opção"]
HYP_CUES = ["pode ser", "acho que", "suponho", "é possível que", "hipoteticamente",
            "reduziria", "resolveria", "melhore", "escalaria", "talvez"]


def deterministic_modality(text: str) -> str | None:
    low = text.lower()
    # order matters: a decision cue is strongest; then hypothesis (epistemic) vs option
    if any(c in low for c in DECISION_CUES):
        return "decision"
    if any(c in low for c in HYP_CUES):
        return "hypothesis"
    if any(c in low for c in OPTION_CUES):
        return "option"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    items = generate(args.n, seed=args.seed)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"modality_{run_id}.jsonl")
    print(f"[modality] model={cfg.model} n={len(items)}")
    print(f"[modality] writing -> {out_path}\n")

    methods = ["lossy", "structured", "deterministic_check"]
    # per method: exact accuracy, upward-inversion count, by-true-modality breakdown
    acc = {m: Counter() for m in methods}
    upinv = {m: 0 for m in methods}
    cost = Counter()

    with open(out_path, "w", encoding="utf-8") as out:
        for i, it in enumerate(items):
            results = {}
            r_lossy = pipe_lossy(client, it.text)
            r_struct = pipe_structured(client, it.text)
            r_det = (deterministic_modality(it.text), "(rule)", 0, 0, 0.0)
            for method, (pred, fact, pt, ct, el) in [
                ("lossy", r_lossy), ("structured", r_struct), ("deterministic_check", r_det)
            ]:
                correct = (pred == it.modality)
                acc[method]["correct" if correct else "wrong"] += 1
                if pred is None:
                    acc[method]["unparsed"] += 1
                if pred is not None and is_upward_inversion(it.modality, pred):
                    upinv[method] += 1
                cost[method] += ct
                results[method] = {"pred": pred, "correct": correct, "fact": fact}
            out.write(json.dumps({
                "i": i, "text": it.text, "true_modality": it.modality,
                "results": results, "model": cfg.model,
            }, ensure_ascii=False) + "\n")
            out.flush()
            print(f"  {i+1}/{len(items)} true={it.modality:10} "
                  f"lossy={str(results['lossy']['pred']):10} "
                  f"struct={str(results['structured']['pred']):10} "
                  f"det={str(results['deterministic_check']['pred'])}")

    n = len(items)
    print("\n" + "=" * 76)
    print("MODALITY PRESERVATION — does structure keep what compression erases?")
    print("=" * 76)
    print(f"{'method':22}{'accuracy':>12}{'UPWARD-INV':>14}{'~tokens':>12}")
    for m in methods:
        a = acc[m]["correct"]
        print(f"{m:22}{a:>7}/{n:<4}{upinv[m]:>9}/{n:<4}{cost[m]:>12}")
    print("\nUPWARD-INVERSION = a hedge (option/hypothesis) recalled as a DECISION.")
    print("The dangerous error — the agent acts on a maybe as if decided.")
    print("\n§5 hypothesis test (deterministic_check): if the rule-based pass on the")
    print("ORIGINAL text matches structured well, modality is BOUNDED/CHECKABLE ->")
    print("the three layers are one principle. If it fails badly, modality needs real")
    print("understanding -> memory is a separate, harder problem.")
    print(f"\n[modality] raw -> {out_path}")


if __name__ == "__main__":
    main()
