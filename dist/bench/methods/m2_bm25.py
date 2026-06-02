import re

from ..chunks import load_chunks
from ..client import ORClient
from ..pricing import cost_usd


def _tokenize(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def run(client: ORClient, task: str, workspace_dir: str, top_k: int = 3, chunk_lines: int = 50, **_) -> dict:
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return {
            "ok": False, "output": "", "error": "rank_bm25 not installed",
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "elapsed_s": 0.0, "turns": 0, "cost_usd": 0.0, "skipped": True,
        }
    chunks = load_chunks(workspace_dir, chunk_lines)
    corpus = [_tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(task))
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    top_idx = order[:top_k]
    retrieved = "\n\n".join(chunks[i]["text"] for i in top_idx)
    prompt = f"Contexto Recuperado (BM25 top-{top_k}):\n{retrieved}\n\nTarefa: {task}"
    r = client.chat([{"role": "user", "content": prompt}])
    return {
        "ok": r.ok,
        "output": r.content,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "total_tokens": r.total_tokens,
        "elapsed_s": r.elapsed_s,
        "turns": 1,
        "cost_usd": cost_usd(client.model, r.prompt_tokens, r.completion_tokens),
        "error": r.error,
        "retrieved": [{"src": chunks[i]["src"], "start": chunks[i]["start"]} for i in top_idx],
    }
