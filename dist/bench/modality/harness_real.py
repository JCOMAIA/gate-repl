"""§5b decisive test: does the FROZEN deterministic marker lexicon survive REAL,
varied conversational text — text whose surface forms it did NOT control?

The prior test was circular: sentences were generated from templates whose markers
the rule knew. Here we remove that crutch:

  1. A GENERATOR LLM produces natural, varied statements for a given modality,
     explicitly told to AVOID the obvious canonical markers and to phrase things
     many different ways (high temperature). Ground truth = the requested modality.
  2. The deterministic lexicon is FROZEN — imported unchanged from harness.py. We
     do NOT expand it after seeing the generated text (that would be tuning).
  3. We measure COVERAGE (fraction the frozen rule can classify at all) alongside
     accuracy and upward-inversion, because a fixed lexicon's expected weakness on
     real text is gaps, not just errors.

Three deciders, as before: lossy (compress→classify), structured (slot), and the
frozen deterministic rule. The question: on text the rule didn't shape, does it
still avoid the dangerous upward-inversion better than the LLM — or do unbounded
surface forms defeat it?

Run:  python -m bench.modality.harness_real --n 30
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
from .dataset import is_upward_inversion, generate as gen_templated
# FROZEN lexicon + the three deciders, imported unchanged
from .harness import (deterministic_modality, pipe_lossy, pipe_structured,
                      DECISION_CUES, OPTION_CUES, HYP_CUES)
from .classifiers import RBFPrototype, SmallLogistic


GEN_P = """Escreva UMA frase curta e NATURAL de uma conversa técnica de equipe, que
expresse claramente um status modal de '{mod}':
  - decision: algo já decidido e comprometido pela equipe.
  - option: uma possibilidade de AÇÃO ainda em consideração (não decidida).
  - hypothesis: uma crença/suposição tentativa sobre fatos (pode estar certa ou não).

IMPORTANTE: varie MUITO a forma. NÃO use estes começos óbvios: "vamos", "poderíamos",
"talvez", "acho que", "decidimos". Use fraseado natural e diverso, como pessoas reais
escrevem no Slack. Escreva só a frase, sem aspas, sem rótulo."""

VALIDATE_P = """Uma pessoa escreveu: "{text}"

O status modal disso é exatamente um de: decision (decidido/comprometido), option
(possibilidade de ação em consideração), hypothesis (crença/suposição tentativa).
Responda só a palavra."""

_WORD = re.compile(r"\b(decision|option|hypothesis)\b", re.IGNORECASE)
MODS = ["decision", "option", "hypothesis"]


def generate_real(client, n_per_mod, seed_base=0):
    """Generate varied natural statements; keep only those whose modality an
    independent judge confirms (so ground truth is reliable despite free phrasing)."""
    items = []
    for mod in MODS:
        made = 0
        attempts = 0
        while made < n_per_mod and attempts < n_per_mod * 3:
            attempts += 1
            g = client.chat([{"role": "user", "content": GEN_P.format(mod=mod)}])
            text = g.content.strip().strip('"').split("\n")[0]
            if len(text) < 8:
                continue
            # independent confirmation of ground truth (blind to requested mod)
            v = client.chat([{"role": "user", "content": VALIDATE_P.format(text=text)}])
            m = _WORD.search(v.content)
            confirmed = m.group(1).lower() if m else None
            if confirmed == mod:        # keep only agreed-modality items
                items.append({"text": text, "modality": mod})
                made += 1
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="approx total items")
    args = ap.parse_args()
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=max(cfg.temperature, 0.9),
                      timeout=cfg.timeout_s)   # high temp for surface variety

    per = max(1, args.n // 3)
    print(f"[modality_real] model={cfg.model} generating ~{per*3} varied items...")
    items = generate_real(client, per)
    print(f"[modality_real] kept {len(items)} judge-confirmed items\n")
    if not items:
        raise SystemExit("generation produced no confirmed items")

    # Train the deterministic non-LLM classifiers ONLY on templated easy text,
    # then test on the real varied items above (generalization test).
    print("[modality_real] fitting RBF + logistic on templated train set...")
    tmpl = gen_templated(90, seed=7)
    rbf = RBFPrototype(tau=8.0).fit([t.text for t in tmpl], [t.modality for t in tmpl])
    clf = SmallLogistic().fit([t.text for t in tmpl], [t.modality for t in tmpl])
    # abstention margin for RBF: calibrate at the 25th percentile of train margins
    import numpy as np
    margins = [rbf.predict(t.text)[1] for t in tmpl]
    rbf_min_margin = float(np.percentile(margins, 25))
    print(f"[modality_real] RBF abstain margin (p25) = {rbf_min_margin:.4f}\n")

    # decisions made deterministically at temp 0 for the LLM deciders is ideal, but
    # we reuse the same client; modality decisions are short and stable enough.
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"modalityreal_{run_id}.jsonl")

    methods = ["lossy", "structured", "frozen_lexicon", "rbf_proto", "rbf_abstain", "small_clf"]
    acc = {m: Counter() for m in methods}
    upinv = {m: 0 for m in methods}
    cover = {m: 0 for m in methods}     # how many it classified at all
    cost = Counter()

    with open(out_path, "w", encoding="utf-8") as out:
        for i, it in enumerate(items):
            text, true = it["text"], it["modality"]
            r_lossy = pipe_lossy(client, text)
            r_struct = pipe_structured(client, text)
            det = deterministic_modality(text)              # FROZEN rule
            rbf_pred, rbf_margin = rbf.predict(text)          # RBF, always answers
            rbf_ab, _ = rbf.predict(text, min_margin=rbf_min_margin)  # RBF w/ abstain
            clf_pred = clf.predict(text)                      # small logistic
            preds = {"lossy": r_lossy[0], "structured": r_struct[0],
                     "frozen_lexicon": det, "rbf_proto": rbf_pred,
                     "rbf_abstain": rbf_ab, "small_clf": clf_pred}
            cost["lossy"] += r_lossy[3]; cost["structured"] += r_struct[3]
            res = {}
            for method, pred in preds.items():
                if pred is not None:
                    cover[method] += 1
                    if pred == true:
                        acc[method]["correct"] += 1
                    if is_upward_inversion(true, pred):
                        upinv[method] += 1
                res[method] = pred
            res["rbf_margin"] = round(rbf_margin, 4)
            out.write(json.dumps({"i": i, "text": text, "true_modality": true,
                                  "preds": res, "model": cfg.model}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"  {i+1}/{len(items)} true={true:10} "
                  f"lossy={str(res['lossy']):8} struct={str(res['structured']):8} "
                  f"rbf={str(res['rbf_proto']):8} clf={str(res['small_clf']):8}")

    n = len(items)
    print("\n" + "=" * 84)
    print("MODALITY ON REAL VARIED TEXT — LLM vs frozen rule vs RBF kernel vs small clf")
    print("=" * 84)
    print(f"{'method':18}{'coverage':>11}{'acc/covered':>14}{'UPWARD-INV':>13}")
    for m in methods:
        cv = cover[m]
        a = acc[m]["correct"]
        accstr = f"{a}/{cv}" if cv else "-"
        print(f"{m:18}{cv:>6}/{n:<4}{accstr:>14}{upinv[m]:>9}/{n:<4}")
    print("\nCOVERAGE = items classified at all (frozen rule / rbf_abstain may return None).")
    print("UPWARD-INVERSION = a hedge classified as a DECISION (the dangerous error).")
    print("\nKey reads:")
    print("  - rbf_proto trained ONLY on templated text, tested on real varied text:")
    print("    if it covers ~all AND its upward-inversion < LLM, the §5 arrow exists as")
    print("    a deterministic kernel classifier (Granville/RBF) — layer [3] is buildable.")
    print("  - rbf_abstain (margin-gated) trades coverage for safety: if it drops")
    print("    upward-inversion toward 0, you get a gate-style safe-but-incomplete decider.")
    print("  - frozen_lexicon coverage is the control: low coverage = fixed rules fail on")
    print("    real text, so the working mechanism is kernel-similarity, not a marker list.")
    print(f"\n[modality_real] raw -> {out_path}")


if __name__ == "__main__":
    main()
