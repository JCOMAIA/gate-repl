import os

from ..chunks import FILES
from ..client import ORClient
from ..pricing import cost_usd


def run(client: ORClient, task: str, workspace_dir: str, **_) -> dict:
    parts = []
    for fn in FILES:
        with open(os.path.join(workspace_dir, fn), encoding="utf-8") as f:
            parts.append(f"=== ARQUIVO: {fn} ===\n{f.read()}")
    system = (
        "You compute answers directly from the provided context. "
        "Do NOT write Python or any code. Do NOT emit code blocks. "
        "Read the data, do the arithmetic in your head, and answer."
    )
    prompt = "Workspace de Arquivos:\n" + "\n\n".join(parts) + f"\n\nTarefa: {task}"
    r = client.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ])
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
    }
