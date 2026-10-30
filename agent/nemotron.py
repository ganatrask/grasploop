"""Nebius Token Factory client: chat completions with retries, a model-ID guard and a cost log.

Why not an off-the-shelf client: an earlier stock proxy hit two traps on this API:
a mistyped model ID returns 404 and a naive retry loop hangs forever, and 429s must be retried
with backoff or they get scored as robot failures. Both are handled here. The key comes from
$NEBIUS_API_KEY only; nothing is written to disk except the usage log.

Callers: agent/loop.py (code generation), judges/vision.py (image review). Usage log lines:
{ts, model, status, attempts, latency_s, prompt_tokens, completion_tokens, reasoning_tokens,
 cost_usd, has_image, tag}
"""
from __future__ import annotations

import json
import os
import time

import requests

TF_URL = "https://api.tokenfactory.nebius.com/v1"

# Short names -> Token Factory IDs. All four survive the 2026-11-09 catalogue removals.
MODELS = {
    "lightning": "nvidia/Nemotron-3_5-Lightning",
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "super_vl": "nvidia/Nemotron-3.5-Super-VL",
    "gpt_oss": "openai/gpt-oss-120b",
}
# $ per 1M tokens (input, output), tokenfactory.nebius.com/model-catalog.md, read 2026-10-27
PRICES = {
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
    "nvidia/Nemotron-3.5-Super-VL": (0.30, 0.90),
    "openai/gpt-oss-120b": (0.15, 0.60),
}


RETRIES = 10  # with backoff min(60, 2**k): about 5 minutes of backoff for a sustained overload


class TokenFactoryError(RuntimeError):
    pass


class TokenFactory:
    def __init__(self, model: str, usage_log: str | None = None, temperature: float = 0.2, max_tokens: int = 12000,
                 timeout_s: float = 300.0, tag: str = "", extra: dict | None = None):
        """`extra` is merged into every request body (e.g. {"reasoning_effort": "low"}). Nemotron 3.5
        Lightning spends 94-100 % of its output on reasoning; at 6,000 tokens a third of replies were
        cut off before the code block (first loop run, 2026-10-27)."""
        self.model = MODELS.get(model, model)
        self.usage_log = usage_log
        self.temperature, self.max_tokens, self.timeout_s, self.tag = temperature, max_tokens, timeout_s, tag
        self.extra = dict(extra or {})
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            raise TokenFactoryError("NEBIUS_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.total_cost_usd = 0.0
        self.calls = 0

    def check_model(self) -> None:
        """Fail now, not after RETRIES retries, if the model ID is not served."""
        r = requests.get(f"{TF_URL}/models", headers=self._headers, timeout=30)
        r.raise_for_status()
        ids = {m["id"] for m in r.json().get("data", [])}
        if self.model not in ids:
            raise TokenFactoryError(f"model {self.model!r} is not served by Token Factory; served: {sorted(ids)}")

    def chat(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None,
             tag: str | None = None) -> dict:
        """Return dict(content, usage, cost_usd, latency_s, status, attempts, finish). Raises TokenFactoryError
        on a non-retryable HTTP error or after RETRIES failed tries (5xx and 429 are retried; HTTP 529
        'System is overloaded' is a real Token Factory reply, 2026-10-27)."""
        body = dict(model=self.model, messages=messages, max_tokens=max_tokens or self.max_tokens,
                    temperature=self.temperature if temperature is None else temperature, **self.extra)
        has_image = any(isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
                        for m in messages)
        t0 = time.time()
        attempts, resp = 0, None
        for attempt in range(RETRIES):
            attempts = attempt + 1
            try:
                resp = requests.post(f"{TF_URL}/chat/completions", headers=self._headers, json=body, timeout=self.timeout_s)
            except requests.RequestException as e:
                if attempt == RETRIES - 1:
                    raise TokenFactoryError(f"request failed after {attempts} attempts: {e}") from e
                time.sleep(min(60, 2 ** attempt))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                time.sleep(min(60, float(retry_after) if retry_after else 2 ** attempt))
                continue
            break
        latency = time.time() - t0
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp is not None else None
            self._log(dict(status=status, attempts=attempts, latency_s=round(latency, 2), has_image=has_image, tag=tag))
            raise TokenFactoryError(f"HTTP {status} from Token Factory: {(resp.text if resp is not None else '')[:300]}")
        data = resp.json()
        u = data.get("usage") or {}
        pin, pout = PRICES.get(self.model, (0.0, 0.0))
        cost = (u.get("prompt_tokens", 0) * pin + u.get("completion_tokens", 0) * pout) / 1e6
        self.total_cost_usd += cost
        self.calls += 1
        choice = (data.get("choices") or [{}])[0]
        out = dict(content=(choice.get("message") or {}).get("content") or "", finish=choice.get("finish_reason"),
                   usage=dict(prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                              reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens")),
                   cost_usd=round(cost, 6), latency_s=round(latency, 2), status=200, attempts=attempts, model=self.model)
        self._log(dict(status=200, attempts=attempts, latency_s=out["latency_s"], **out["usage"], cost_usd=out["cost_usd"],
                       has_image=has_image, tag=tag))
        return out

    def _log(self, rec: dict) -> None:
        if not self.usage_log:
            return
        rec = dict(ts=round(time.time(), 3), model=self.model, tag=rec.pop("tag", None) or self.tag, **rec)
        os.makedirs(os.path.dirname(self.usage_log) or ".", exist_ok=True)
        with open(self.usage_log, "a") as f:
            f.write(json.dumps(rec) + "\n")


def extract_code(text: str) -> str:
    """The program from a model reply: the last ```python fence, else the last fence, else the text."""
    import re
    fences = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    if fences:
        return fences[-1].strip("\n")
    return text.strip()
