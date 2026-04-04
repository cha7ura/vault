"""Shared LLM client — uses OpenRouter if key set, otherwise Ollama."""
import json
import re

import requests

from scripts.agents.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL


def llm_call(prompt: str, temperature: float = 0.3, think: bool = False) -> str:
    """Send a prompt to LLM and return the response text."""
    prefix = "" if think else "/no_think\n"
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
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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
