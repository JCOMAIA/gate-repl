import json
import os
import time
import traceback

from . import config, evaluator, workspace
from .client import ORClient
from .methods import m1_brute, m2_bm25, m3_embed, m4_rlm


METHODS = {
    "m1_brute": m1_brute.run,
    "m2_bm25": m2_bm25.run,
    "m3_embed": m3_embed.run,
    "m4_rlm": m4_rlm.run,
}


def _safe_run(fn, client, task, cfg):
    try:
        return fn(
            client,
            task,
            cfg.workspace_dir,
            top_k=cfg.rag_top_k,
            chunk_lines=cfg.rag_chunk_lines,
            max_turns=cfg.max_turns_rlm,
        )
    except Exception as e:
        return {
            "ok": False,
            "output": "",
            "error": f"exception: {e}\n{traceback.format_exc()}",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "elapsed_s": 0.0,
            "turns": 0,
            "cost_usd": 0.0,
        }


def _skipped(reason: str) -> dict:
    return {
        "ok": False, "output": "", "error": reason, "skipped": True,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "elapsed_s": 0.0, "turns": 0, "cost_usd": 0.0,
    }


def main() -> None:
    cfg = config.from_env()
    os.makedirs(cfg.results_dir, exist_ok=True)
    client = ORClient(cfg.api_key, cfg.model, temperature=cfg.temperature, timeout=cfg.timeout_s)
    target = workspace.GROUND_TRUTH
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(cfg.results_dir, f"trials_{run_id}.jsonl")
    active_methods = {k: v for k, v in METHODS.items() if (not cfg.methods or k in cfg.methods)}
    if not active_methods:
        raise SystemExit(f"BENCH_METHODS={cfg.methods} matched no known method. Available: {list(METHODS)}")
    total_calls = len(cfg.scales) * len(active_methods) * cfg.n_trials
    print(f"[runner] model={cfg.model} scales={list(cfg.scales)} trials={cfg.n_trials} "
          f"({total_calls} runs total) target={target}")
    print(f"[runner] writing -> {out_path}")

    with open(out_path, "w", encoding="utf-8") as out:
        for scale in cfg.scales:
            print(f"\n[runner] === scale = {scale} lines/file ===")
            workspace.generate(cfg.workspace_dir, n_lines=scale)
            for method_name, fn in active_methods.items():
                for trial in range(cfg.n_trials):
                    skip_m1 = method_name == "m1_brute" and scale > cfg.skip_m1_above_lines
                    label = f"  - {method_name}@{scale} trial {trial + 1}/{cfg.n_trials}"
                    print(label, end=" ... ", flush=True)
                    if skip_m1:
                        res = _skipped(f"skipped: scale {scale} > cap {cfg.skip_m1_above_lines}")
                    else:
                        res = _safe_run(fn, client, workspace.TASK, cfg)
                    parsed = evaluator.extract_final_number(res.get("output", ""))
                    res["parsed_value"] = parsed
                    res["target"] = target
                    res["success"] = evaluator.matches(parsed, target)
                    res["method"] = method_name
                    res["trial"] = trial
                    res["scale"] = scale
                    res["model"] = cfg.model
                    out.write(json.dumps(res, ensure_ascii=False) + "\n")
                    out.flush()
                    status = "OK" if res["success"] else ("SKIP" if res.get("skipped") else "FAIL")
                    err = (res.get("error") or "")[:60]
                    print(f"{status} value={parsed} tokens={res.get('total_tokens', 0)} "
                          f"t={res.get('elapsed_s', 0):.1f}s err={err}")
    print(f"\n[runner] done -> {out_path}")
    print("[runner] next: python -m bench.report")


if __name__ == "__main__":
    main()
