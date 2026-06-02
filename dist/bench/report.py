import glob
import json
import os
import statistics
import sys
from collections import defaultdict

from . import config


def _latest(results_dir: str) -> str:
    files = sorted(glob.glob(os.path.join(results_dir, "trials_*.jsonl")))
    if not files:
        raise SystemExit("No trials found. Run `python -m bench.runner` first.")
    return files[-1]


def _ms(xs: list[float]) -> str:
    if not xs:
        return "n/a"
    if len(xs) == 1:
        return f"{xs[0]:.1f}"
    return f"{statistics.mean(xs):.1f} ± {statistics.pstdev(xs):.1f}"


def main() -> None:
    cfg = config.from_env()
    path = sys.argv[1] if len(sys.argv) > 1 else _latest(cfg.results_dir)
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    if not rows:
        raise SystemExit(f"No rows in {path}")

    # group by (method, scale)
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        scale = r.get("scale", 1000)
        grouped[(r["method"], scale)].append(r)

    methods = sorted({m for m, _ in grouped.keys()})
    scales = sorted({s for _, s in grouped.keys()})
    model = rows[0]["model"]
    target = rows[0]["target"]

    lines: list[str] = [
        "# Benchmark Report",
        "",
        f"- File: `{path}`",
        f"- Model: `{model}`",
        f"- Target value: `{target}`",
        f"- Scales (lines/file): {scales}",
        f"- Trials per (method, scale): {len(next(iter(grouped.values())))}",
        "",
    ]

    # --- Matrix 1: success rate ---
    lines += [
        "## Success rate by scale",
        "",
        "| Method \\ Scale | " + " | ".join(f"{s}" for s in scales) + " |",
        "| :--- | " + " | ".join(":---:" for _ in scales) + " |",
    ]
    for m in methods:
        cells = []
        for s in scales:
            runs = grouped.get((m, s), [])
            if not runs:
                cells.append("—")
                continue
            n = len(runs)
            wins = sum(1 for r in runs if r["success"])
            skipped = sum(1 for r in runs if r.get("skipped"))
            if skipped == n:
                cells.append("skip")
            else:
                cells.append(f"{int(wins / n * 100)}% ({wins}/{n})")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- Matrix 2: total tokens (mean) ---
    lines += [
        "## Mean total tokens by scale",
        "",
        "| Method \\ Scale | " + " | ".join(f"{s}" for s in scales) + " |",
        "| :--- | " + " | ".join(":---:" for _ in scales) + " |",
    ]
    for m in methods:
        cells = []
        for s in scales:
            runs = [r for r in grouped.get((m, s), []) if not r.get("skipped")]
            if not runs:
                cells.append("—")
            else:
                cells.append(_ms([r.get("total_tokens", 0) for r in runs]))
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- Matrix 3: latency ---
    lines += [
        "## Mean latency (s) by scale",
        "",
        "| Method \\ Scale | " + " | ".join(f"{s}" for s in scales) + " |",
        "| :--- | " + " | ".join(":---:" for _ in scales) + " |",
    ]
    for m in methods:
        cells = []
        for s in scales:
            runs = [r for r in grouped.get((m, s), []) if not r.get("skipped")]
            if not runs:
                cells.append("—")
            else:
                cells.append(_ms([r.get("elapsed_s", 0.0) for r in runs]))
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- Matrix 4: mean cost USD ---
    lines += [
        "## Mean cost USD by scale",
        "",
        "| Method \\ Scale | " + " | ".join(f"{s}" for s in scales) + " |",
        "| :--- | " + " | ".join(":---:" for _ in scales) + " |",
    ]
    for m in methods:
        cells = []
        for s in scales:
            runs = [r for r in grouped.get((m, s), []) if not r.get("skipped")]
            if not runs:
                cells.append("—")
            else:
                cells.append(f"{statistics.mean([r.get('cost_usd', 0.0) for r in runs]):.5f}")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- Per-trial details ---
    lines += ["## Per-trial outputs (truncated)", ""]
    for s in scales:
        lines.append(f"### scale = {s}")
        for m in methods:
            runs = grouped.get((m, s), [])
            if not runs:
                continue
            lines.append(f"\n**{m}**")
            for r in runs:
                out = (r.get("output") or "").replace("\n", " ")[:120]
                err = (r.get("error") or "")[:80]
                mark = "OK" if r["success"] else ("SKIP" if r.get("skipped") else "FAIL")
                lines.append(
                    f"- trial {r['trial']}: **{mark}** parsed=`{r.get('parsed_value')}` "
                    f"tokens={r.get('total_tokens', 0)} t={r.get('elapsed_s', 0):.1f}s "
                    f"err=`{err}` out=`{out}`"
                )
        lines.append("")

    report = "\n".join(lines)
    report_path = path.replace(".jsonl", ".md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\n[report] saved -> {report_path}")


if __name__ == "__main__":
    main()
