"""LLM calls for wiki extraction (Groq) and episode summary (OpenRouter)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from scripts.agents.config import (
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    WIKI_EXTRACT_MODEL,
    WIKI_SUMMARY_MODEL,
)
from scripts.agents.db import log_llm_usage
from scripts.agents.llm import log_llm_call as _log_call

_GROQ_BASE = "https://api.groq.com/openai/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_EMPTY = {"entities": [], "edges": [], "observations": []}

# Groq strict structured outputs require every object to have
# `additionalProperties: false` and every field in `required`. Open-ended
# attribute dicts are modeled as arrays of {key, value} pairs and converted
# back to dicts on the Python side.
_KV_PAIR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key", "value"],
    "properties": {
        "key": {"type": "string"},
        "value": {"type": "string"},
    },
}

_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities", "edges", "observations"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "name", "slug", "attributes"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "Person", "Organization", "Concept", "Work",
                            "Method", "Product", "Podcast", "Event", "Place",
                        ],
                    },
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "attributes": {"type": "array", "items": _KV_PAIR_SCHEMA},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "type", "from_name", "from_type",
                    "to_name", "to_type", "attributes", "episode",
                ],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "Hosts", "AppearsOn", "WorksWith", "AffiliatedWith",
                            "Claims", "Recommends", "Describes", "References",
                            "Sponsors", "RelatesTo",
                        ],
                    },
                    "from_name": {"type": "string"},
                    "from_type": {"type": "string"},
                    "to_name": {"type": "string"},
                    "to_type": {"type": "string"},
                    "attributes": {"type": "array", "items": _KV_PAIR_SCHEMA},
                    "episode": {"type": "string"},
                },
            },
        },
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["entity_name", "episode", "timestamp", "text"],
                "properties": {
                    "entity_name": {"type": "string"},
                    "episode": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
}


def _kv_to_dict(pairs: list | None) -> dict:
    if not pairs:
        return {}
    return {p.get("key", ""): p.get("value", "") for p in pairs if p.get("key")}


def _recover_from_failed_generation(resp) -> dict | None:
    """If Groq's strict validator rejected output, recover the partial JSON.

    Groq returns ``{"error": {"code": "json_validate_failed",
    "failed_generation": "<raw json>"}}`` — the LLM output is almost always
    usable once missing required arrays (entities/edges/observations) are
    filled in with ``[]``.

    Returns the normalized dict, or None if recovery fails.
    """
    try:
        payload = resp.json()
    except Exception:
        return None
    err = payload.get("error") or {}
    if err.get("code") != "json_validate_failed":
        return None
    raw = err.get("failed_generation")
    if not raw:
        return None
    try:
        partial = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(partial, dict):
        return None
    partial.setdefault("entities", [])
    partial.setdefault("edges", [])
    partial.setdefault("observations", [])
    print(
        f"  RECOVER: salvaged {len(partial['entities'])} entities, "
        f"{len(partial['edges'])} edges from failed_generation"
    )
    return partial


def _strip_markdown_fence(text: str) -> str:
    """Strip leading/trailing ```...``` fences that GLM-5.1 wraps around output."""
    s = text.strip()
    if s.startswith("```"):
        # drop the opening fence line
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
    if s.endswith("```"):
        s = s[:-3].rstrip()
    return s

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
- If an EPISODE block is provided, use ``podcast_name`` / ``podcast_slug`` verbatim for the Podcast entity and the Hosts/AppearsOn edges. NEVER emit "Unnamed Podcast" or invent a different show name. Use ``host_name`` for the podcast's host and ``guest_name`` as the primary guest for AppearsOn edges.
- Use the ``youtube_id`` from the EPISODE block as the ``episode`` field on every edge and observation. Never emit the literal string "YOUTUBE_ID" or "unknown".
- AffiliatedWith edges MUST include a role attribute (investor/founder/ceo/employee/advisor/board_member).
- For Claims edges, include insight_type (claim/advice/tip/warning) and timestamp if available.
- Do NOT invent new edge types. Use RelatesTo as the fallback.
- If you notice something interesting that doesn't fit — partial names, unclear entities, possible new frameworks — add it to observations. Never discard it.

OUTPUT FORMAT (JSON object, strict schema enforced):
- "attributes" is an ARRAY of {"key": "...", "value": "..."} pairs (NOT a dict).
  This is required by the strict schema validator.

Example:
{
  "entities": [
    {"type": "Person", "name": "Full Name", "slug": "full-name",
     "attributes": [{"key": "expertise", "value": "Neuroscience"}]}
  ],
  "edges": [
    {"type": "Claims", "from_name": "Full Name", "from_type": "Person",
     "to_name": "Concept Name", "to_type": "Concept",
     "attributes": [
       {"key": "insight_type", "value": "claim"},
       {"key": "timestamp", "value": "14:23"}
     ],
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
output a raw markdown file with YAML front matter. Output ONLY the file
contents — no code fences, no ```markdown blocks, no explanatory text.

FORMAT (exactly):
---
type: episode
youtube_id: <id>
title: <title>
date: <date>
guest: "[[people/<guest-slug>]]"
host: "[[people/steven-bartlett]]"
podcast: "[[podcasts/diary-of-a-ceo]]"
topics:
  - "[[concepts/<slug>]]"
works_referenced:
  - "[[works/<slug>]]"
---

## Summary
(2-3 sentences)

## Key Claims
- (bullet list with [[wikilinks]] and timestamps)

## References
- (books/papers cited, if any)

The first three characters of your response must be `---`. Use [[wikilinks]]
throughout. Be concise.
"""


def extract_chunk_json(
    chunk_text: str,
    index_content: str,
    episode_id: str | None = None,
    episode_meta: dict | None = None,
) -> dict:
    """Call Groq to extract entities/edges from a transcript chunk.

    ``episode_meta`` should carry known metadata (youtube_id, title,
    published_at, guest_name, podcast_name, podcast_slug, host_name). When
    present it is prefixed to ``user_content`` so the LLM never has to guess
    the show name and never falls back to ``[[podcasts/unnamed-podcast]]``.

    Returns extraction dict with keys: entities, edges, observations.
    Returns empty structure on any error (pipeline continues).
    """
    if not GROQ_API_KEY:
        print("  WARN: GROQ_API_KEY not set — skipping extraction")
        return dict(_EMPTY)

    meta_lines = []
    if episode_meta:
        for key in ("youtube_id", "title", "published_at", "guest_name",
                    "host_name", "podcast_name", "podcast_slug"):
            val = episode_meta.get(key)
            if val:
                meta_lines.append(f"{key}: {val}")
    episode_block = "EPISODE:\n" + "\n".join(meta_lines) + "\n\n" if meta_lines else ""

    user_content = (
        f"{episode_block}"
        f"INDEX:\n{index_content}\n\nTRANSCRIPT:\n{chunk_text}"
    )
    t0 = time.monotonic()
    try:
        resp = requests.post(
            f"{_GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": WIKI_EXTRACT_MODEL,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "wiki_extraction",
                        "strict": True,
                        "schema": _EXTRACTION_SCHEMA,
                    },
                },
                "messages": [
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0,
                # Give the strict JSON generator enough headroom to finish the
                # document. Groq's default cap truncates dense chunks mid-array
                # and produces `max completion tokens reached` 400s that can't
                # be recovered (the partial is unparseable).
                "max_completion_tokens": 8192,
            },
            timeout=120,
        )
    except requests.RequestException as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        print(f"  WARN: Groq request failed: {e}")
        log_llm_usage(
            episode_id=episode_id, stage="wiki_extract", provider="groq",
            model=WIKI_EXTRACT_MODEL, status_code=0,
            duration_ms=duration_ms, error=str(e),
        )
        return dict(_EMPTY)

    duration_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        # Groq strict mode returns 400 + `failed_generation` when the LLM
        # omits a required key (commonly an empty `observations: []`). The
        # partial JSON is still usable — parse it and backfill the gaps.
        result = _recover_from_failed_generation(resp)
        try:
            error_payload = resp.json()
        except Exception:
            error_payload = None
        # Extract the short error message so the llm_usage row tells us
        # *why* it failed, not just that it did. Always log it — even on
        # successful recovery, so we can track how often we're salvaging.
        err_msg = None
        if error_payload:
            err_msg = (error_payload.get("error") or {}).get("message")
        if not err_msg:
            err_msg = resp.text[:500]
        if result is not None:
            err_msg = f"recovered: {err_msg}"
        _log_call(
            episode_id=episode_id, stage="wiki_extract", provider="groq",
            model=WIKI_EXTRACT_MODEL, status_code=resp.status_code,
            payload=error_payload, duration_ms=duration_ms,
            error=err_msg[:500] if err_msg else None,
        )
        if result is None:
            print(f"  WARN: Groq returned {resp.status_code}: {resp.text[:2000]}")
            return dict(_EMPTY)
    else:
        try:
            payload = resp.json()
            _log_call(
                episode_id=episode_id, stage="wiki_extract", provider="groq",
                model=WIKI_EXTRACT_MODEL, status_code=200,
                payload=payload, duration_ms=duration_ms,
            )
            raw = payload["choices"][0]["message"]["content"]
            result = json.loads(raw)
        except (KeyError, json.JSONDecodeError) as e:
            print(f"  WARN: Could not parse Groq response: {e}")
            return dict(_EMPTY)

    # Convert KV-pair arrays back to dicts so wiki_writer receives its
    # expected shape (attributes as a dict).
    entities = []
    for ent in result.get("entities") or []:
        entities.append({
            "type": ent.get("type", ""),
            "name": ent.get("name", ""),
            "slug": ent.get("slug", ""),
            "attributes": _kv_to_dict(ent.get("attributes")),
        })
    edges = []
    for edge in result.get("edges") or []:
        edges.append({
            "type": edge.get("type", ""),
            "from_name": edge.get("from_name", ""),
            "from_type": edge.get("from_type", ""),
            "to_name": edge.get("to_name", ""),
            "to_type": edge.get("to_type", ""),
            "attributes": _kv_to_dict(edge.get("attributes")),
            "episode": edge.get("episode", ""),
        })
    return {
        "entities": entities,
        "edges": edges,
        "observations": result.get("observations") or [],
    }


def write_episode_summary(
    episode: dict,
    touched_page_texts: list[str],
    wiki_dir: Path,
) -> None:
    """Generate and save an episode summary page via OpenRouter.

    episode: dict with keys episode_id, youtube_id, title, published_at, guest_name (optional)
    touched_page_texts: list of raw .md file contents for pages touched this episode
    """
    if not OPENROUTER_API_KEY:
        print("  WARN: OPENROUTER_API_KEY not set — skipping episode summary")
        return

    episode_id = episode.get("episode_id")
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

    t0 = time.monotonic()
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
                # Return authoritative usage.cost on the response.
                "usage": {"include": True},
            },
            timeout=120,
        )
    except requests.RequestException as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        print(f"  WARN: OpenRouter request failed: {e}")
        log_llm_usage(
            episode_id=episode_id, stage="wiki_summary", provider="openrouter",
            model=WIKI_SUMMARY_MODEL, status_code=0,
            duration_ms=duration_ms, error=str(e),
        )
        return

    duration_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        print(f"  WARN: OpenRouter returned {resp.status_code}: {resp.text[:500]}")
        log_llm_usage(
            episode_id=episode_id, stage="wiki_summary", provider="openrouter",
            model=WIKI_SUMMARY_MODEL, status_code=resp.status_code,
            duration_ms=duration_ms, error=resp.text[:500],
        )
        return

    try:
        payload = resp.json()
        _log_call(
            episode_id=episode_id, stage="wiki_summary", provider="openrouter",
            model=WIKI_SUMMARY_MODEL, status_code=200,
            payload=payload, duration_ms=duration_ms,
        )
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, Exception) as e:
        print(f"  WARN: Could not parse OpenRouter response: {e}")
        return

    content = _strip_markdown_fence(content)

    ep_path = wiki_dir / "_episodes" / f"{youtube_id}.md"
    ep_path.parent.mkdir(parents=True, exist_ok=True)
    # Prepend a comment with the youtube_id so it's always present in the file
    file_content = f"<!-- youtube_id: {youtube_id} -->\n{content}"
    ep_path.write_text(file_content, encoding="utf-8")
    print(f"  Episode summary: {ep_path.name}")
