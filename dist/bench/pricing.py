from functools import lru_cache

import requests


@lru_cache(maxsize=1)
def _model_index() -> dict:
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        return {m["id"]: m for m in data}
    except Exception:
        return {}


def get_prices(model_id: str) -> tuple[float | None, float | None]:
    idx = _model_index()
    if model_id not in idx:
        return None, None
    p = idx[model_id].get("pricing", {}) or {}
    try:
        return float(p.get("prompt", 0)), float(p.get("completion", 0))
    except (TypeError, ValueError):
        return None, None


def cost_usd(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = get_prices(model_id)
    if pin is None or pout is None:
        return 0.0
    return pin * prompt_tokens + pout * completion_tokens
