"""LLM calls for wiki extraction (Groq) and episode summary (OpenRouter)."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from scripts.agents.config import (
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    WIKI_EXTRACT_MODEL,
    WIKI_SUMMARY_MODEL,
)

_GROQ_BASE = "https://api.groq.com/openai/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_EMPTY = {"entities": [], "edges": [], "observations": []}

_EXTRACT_SYSTEM = """\
You extract structured knowledge from podcast transcript segments.

ENTITY TYPES (use exactly these names):
Person, Organization, Concept, Work, Method, Product, Podcast, Event, Place

EDGE TYPES (use exactly these names):
Hosts, AppearsOn, WorksWith, AffiliatedWith, Claims, Recommends, Describes, References, Sponsors, RelatesTo

RULES:
- Every person is Person (host, guest, anyone referenced). Do NOT use Guest or Host as a type.
- Companies, universities, labs = Organization (include org_type attribute: company/university/lab/media)
- Books and papers = Work (include work_type: book/paper)
- Subject areas, theories, ideas = Concept
- Actionable routines, protocols = Method
- Supplements, apps, tools, devices = Product
- The podcast show itself = Podcast

- Check the INDEX below before naming entities. Use the CANONICAL NAME from the index if a match exists.
- AffiliatedWith edges MUST include a role attribute (investor/founder/ceo/employee/advisor/board_member).
- For Claims edges, include insight_type (claim/advice/tip/warning) and timestamp if available.
- Do NOT invent new edge types. Use RelatesTo as the fallback.
- If you notice something interesting that doesn't fit — partial names, unclear entities, possible new frameworks — add it to observations. Never discard it.

OUTPUT FORMAT (JSON object, no markdown):
{
  "entities": [
    {"type": "Person", "name": "Full Name", "slug": "full-name", "attributes": {"key": "value"}}
  ],
  "edges": [
    {"type": "Claims", "from_name": "Full Name", "from_type": "Person",
     "to_name": "Concept Name", "to_type": "Concept",
     "attributes": {"insight_type": "claim", "timestamp": "14:23", "youtube_url": "..."},
     "episode": "YOUTUBE_ID"}
  ],
  "observations": [
    {"entity_name": "Full Name", "episode": "YOUTUBE_ID", "timestamp": "31:12",
     "text": "what you noticed"}
  ]
}
"""

_SUMMARY_SYSTEM = """\
You write concise episode summary pages for a podcast knowledge wiki.

Given an episode's metadata and the entity pages touched during extraction,
write a markdown episode page with YAML front matter.

The front matter must include:
  type: episode
  youtube_id: <id>
  title: <title>
  date: <date>
  guest: "[[people/<guest-slug>]]"  (if known)
  host: "[[people/steven-bartlett]]"
  podcast: "[[podcasts/diary-of-a-ceo]]"
  topics: list of "[[concepts/slug]]" wikilinks for main topics
  works_referenced: list of "[[works/slug]]" wikilinks (if any)

After the front matter, write:
  ## Summary  (2-3 sentences)
  ## Key Claims  (bullet list of notable claims with [[wikilinks]] and timestamps)
  ## References  (books/papers cited, if any)

Use [[wikilinks]] throughout. Be concise.
"""


def extract_chunk_json(chunk_text: str, index_content: str) -> dict:
    """Call Groq to extract entities/edges from a transcript chunk.

    Returns extraction dict with keys: entities, edges, observations.
    Returns empty structure on any error (pipeline continues).
    """
    if not GROQ_API_KEY:
        print("  WARN: GROQ_API_KEY not set — skipping extraction")
        return dict(_EMPTY)

    user_content = f"INDEX:\n{index_content}\n\nTRANSCRIPT:\n{chunk_text}"
    try:
        resp = requests.post(
            f"{_GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": WIKI_EXTRACT_MODEL,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
            },
            timeout=60,
        )
    except requests.RequestException as e:
        print(f"  WARN: Groq request failed: {e}")
        return dict(_EMPTY)

    if resp.status_code != 200:
        print(f"  WARN: Groq returned {resp.status_code}: {resp.text[:200]}")
        return dict(_EMPTY)

    try:
        raw = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(raw)
        return {
            "entities": result.get("entities") or [],
            "edges": result.get("edges") or [],
            "observations": result.get("observations") or [],
        }
    except (KeyError, json.JSONDecodeError) as e:
        print(f"  WARN: Could not parse Groq response: {e}")
        return dict(_EMPTY)


def write_episode_summary(
    episode: dict,
    touched_page_texts: list[str],
    wiki_dir: Path,
) -> None:
    """Generate and save an episode summary page via OpenRouter.

    episode: dict with keys youtube_id, title, published_at, guest_name (optional)
    touched_page_texts: list of raw .md file contents for pages touched this episode
    """
    if not OPENROUTER_API_KEY:
        print("  WARN: OPENROUTER_API_KEY not set — skipping episode summary")
        return

    youtube_id = episode.get("youtube_id", "unknown")
    title = episode.get("title", "")
    published_at = episode.get("published_at", "")
    guest_name = episode.get("guest_name", "")

    context_pages = "\n\n---\n\n".join(touched_page_texts[:20])
    user_content = (
        f"Episode ID: {youtube_id}\n"
        f"Title: {title}\n"
        f"Date: {published_at}\n"
        f"Guest: {guest_name}\n\n"
        f"ENTITY PAGES TOUCHED THIS EPISODE:\n{context_pages}"
    )

    try:
        resp = requests.post(
            f"{_OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": WIKI_SUMMARY_MODEL,
                "messages": [
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
            },
            timeout=120,
        )
    except requests.RequestException as e:
        print(f"  WARN: OpenRouter request failed: {e}")
        return

    if resp.status_code != 200:
        print(f"  WARN: OpenRouter returned {resp.status_code}: {resp.text[:200]}")
        return

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, Exception) as e:
        print(f"  WARN: Could not parse OpenRouter response: {e}")
        return

    ep_path = wiki_dir / "_episodes" / f"{youtube_id}.md"
    ep_path.parent.mkdir(parents=True, exist_ok=True)
    # Prepend a comment with the youtube_id so it's always present in the file
    file_content = f"<!-- youtube_id: {youtube_id} -->\n{content}"
    ep_path.write_text(file_content, encoding="utf-8")
    print(f"  Episode summary: {ep_path.name}")
