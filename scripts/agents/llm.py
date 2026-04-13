"""Shared LLM client — uses OpenRouter if key set, otherwise Ollama."""
import json
import re

import requests

from scripts.agents.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, groq_cost_usd
from scripts.agents.db import log_llm_usage


def log_llm_call(
    *,
    episode_id: str | None,
    stage: str,
    provider: str,
    model: str,
    status_code: int,
    payload: dict | None,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """Extract usage from an OpenAI-compatible response and persist to llm_usage.

    Shared by every stage that talks to an OpenAI-compatible provider:
      - OpenRouter returns authoritative ``usage.cost`` when the request
        includes ``usage: {include: true}``.
      - Groq does not return cost; we compute from tokens × price list.
    """
    usage = (payload or {}).get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    reasoning_tokens = int(
        ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0
    )
    cached_input_tokens = int(
        ((usage.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    )
    if provider == "openrouter":
        cost_usd = float(usage.get("cost") or 0.0)
    elif provider == "groq":
        cost_usd = groq_cost_usd(model, prompt_tokens, completion_tokens)
    else:
        cost_usd = 0.0

    finish_reason = None
    request_id = (payload or {}).get("id")
    choices = (payload or {}).get("choices") or []
    if choices:
        finish_reason = choices[0].get("finish_reason")

    log_llm_usage(
        episode_id=episode_id,
        stage=stage,
        provider=provider,
        model=model,
        status_code=status_code,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=cached_input_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        request_id=request_id,
        finish_reason=finish_reason,
        duration_ms=duration_ms,
        error=error,
        raw_usage=usage or None,
    )


def llm_call(prompt: str, temperature: float = 0.3, think: bool = False, max_retries: int = 3) -> str:
    """Send a prompt to LLM and return the response text. Retries on 429."""
    import time
    prefix = "" if think else "/no_think\n"

    for attempt in range(max_retries):
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": f"{prefix}{prompt}"}],
                "stream": False,
                "temperature": temperature,
            },
            timeout=300,
        )
        if resp.status_code == 429:
            wait = (attempt + 1) * 10  # 10s, 20s, 30s
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    resp.raise_for_status()  # raise on final failure
    return ""


def llm_json_call(prompt: str, temperature: float = 0.1) -> dict | None:
    """Send a prompt and parse the response as JSON."""
    text = llm_call(prompt, temperature=temperature)
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def check_usage():
    """Check OpenRouter usage stats. Returns dict or None."""
    if "openrouter" not in LLM_BASE_URL:
        return None
    resp = requests.get(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        timeout=10,
    )
    return resp.json().get("data", {})
