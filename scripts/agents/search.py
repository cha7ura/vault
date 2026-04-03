"""SearXNG search client for entity enrichment."""
import requests

from scripts.agents.config import SEARXNG_URL


def searxng_search(
    query: str,
    engines: str = "google",
    max_results: int = 5,
) -> list[dict]:
    """Search via local SearXNG instance. Returns list of {title, url, content}."""
    try:
        resp = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "engines": engines,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[:max_results]
    except Exception:
        return []
