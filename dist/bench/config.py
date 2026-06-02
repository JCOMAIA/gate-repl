import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class BenchConfig:
    api_key: str
    model: str
    n_trials: int = 5
    temperature: float = 0.0
    max_turns_rlm: int = 10
    timeout_s: float = 300.0
    workspace_dir: str = "workspace"
    results_dir: str = "results"
    rag_top_k: int = 3
    rag_chunk_lines: int = 50
    scales: tuple[int, ...] = (1000,)
    skip_m1_above_lines: int = 50000
    methods: tuple[str, ...] = ()  # empty = all methods


def from_env() -> BenchConfig:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. "
            "Create a .env file in the project root (see .env.example) "
            "or export it in your shell."
        )
    raw_scales = os.environ.get("BENCH_SCALES", "1000")
    scales = tuple(int(s.strip()) for s in raw_scales.split(",") if s.strip())
    raw_methods = os.environ.get("BENCH_METHODS", "")
    methods = tuple(m.strip() for m in raw_methods.split(",") if m.strip())
    return BenchConfig(
        api_key=key,
        model=os.environ.get("BENCH_MODEL", "meta-llama/llama-3.1-8b-instruct"),
        n_trials=int(os.environ.get("BENCH_TRIALS", "5")),
        temperature=float(os.environ.get("BENCH_TEMP", "0.0")),
        max_turns_rlm=int(os.environ.get("BENCH_MAX_TURNS", "10")),
        scales=scales,
        timeout_s=float(os.environ.get("BENCH_TIMEOUT", "300")),
        skip_m1_above_lines=int(os.environ.get("BENCH_SKIP_M1_ABOVE", "50000")),
        methods=methods,
    )
