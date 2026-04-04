"""Shared Ollama LLM client for pipeline stages."""
import json
import re

import requests

from scripts.agents.config import OLLAMA_BASE_URL, OLLAMA_MODEL


def llm_call(prompt: str, temperature: float = 0.3, think: bool = False) -> str:
    """Send a prompt to Ollama and return the response text."""
    prefix = "" if think else "/no_think\n"
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": f"{prefix}{prompt}"}],
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


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
