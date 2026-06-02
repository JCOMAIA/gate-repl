import json
import time
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class CallResult:
    ok: bool
    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed_s: float = 0.0
    error: str = ""
    raw: dict = field(default_factory=dict)


class ORClient:
    def __init__(self, api_key: str, model: str, temperature: float = 0.0, timeout: float = 120.0):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict[str, Any]]) -> CallResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        start = time.time()
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout,
            )
            elapsed = time.time() - start
            j = r.json()
            if "choices" not in j:
                err = j.get("error", j)
                return CallResult(ok=False, elapsed_s=elapsed, error=str(err)[:500], raw=j)
            choice = j["choices"][0]
            usage = j.get("usage", {}) or {}
            return CallResult(
                ok=True,
                content=choice["message"].get("content") or "",
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage.get("completion_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
                elapsed_s=elapsed,
                raw=j,
            )
        except Exception as e:
            return CallResult(ok=False, elapsed_s=time.time() - start, error=str(e))
