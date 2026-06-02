from ..chunks import load_chunks
from ..client import ORClient
from ..pricing import cost_usd


_MODEL = None
_CACHE: dict = {}


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL


def run(client: ORClient, task: str, workspace_dir: str, top_k: int = 3, chunk_lines: int = 50, **_) -> dict:
    try:
        import numpy as np
        model = _get_model()
    except ImportError as e:
        return {
            "ok": False, "output": "", "error": f"missing dep: {e}",
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "elapsed_s": 0.0, "turns": 0, "cost_usd": 0.0, "skipped": True,
        }
    chunks = load_chunks(workspace_dir, chunk_lines)
    cache_key = (workspace_dir, chunk_lines)
    if cache_key not in _CACHE:
        _CACHE[cache_key] = model.encode(
            [c["text"] for c in chunks],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    chunk_emb = _CACHE[cache_key]
    q_emb = model.encode([task], normalize_embeddings=True, show_progress_bar=False)[0]
    sims = chunk_emb @ q_emb
    top_idx = np.argsort(-sims)[:top_k].tolist()
    retrieved = "\n\n".join(chunks[i]["text"] for i in top_idx)
    prompt = f"Contexto Recuperado (Embeddings top-{top_k}):\n{retrieved}\n\nTarefa: {task}"
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
