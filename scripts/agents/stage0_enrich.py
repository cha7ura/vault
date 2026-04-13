"""Stage 0 — ENRICH: Web search guest profiles via SearXNG + LLM structuring.

Full accounting: every SearXNG call is logged to ``searxng_usage`` and every
LLM call to ``llm_usage`` (stage='stage0_enrich'). The raw search URLs that
informed each profile are persisted to ``people.sources`` so the wiki writer
can render a ``## Sources`` section on the page.
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from scripts.agents.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_PROVIDER,
)
from scripts.agents.db import execute, fetch_all
from scripts.agents.llm import log_llm_call
from scripts.agents.search import searxng_search


STAGE = "stage0_enrich"

# db.py uses a single Postgres connection that is NOT thread-safe, so any DB
# call reachable from worker threads (log_llm_usage from _llm_call_logged)
# must serialize on this lock.
_DB_LOCK = threading.Lock()


PROFILE_PROMPT = """Extract a structured profile from these search results about "{name}".

CONTEXT — they appeared as a guest on the Diary of a CEO podcast in this episode:
Episode title: {episode_title}
Episode description (first 500 chars): {episode_description}

Use the episode title/description to pick the correct person when search results
return multiple people with this name. If the top results describe someone whose
biography is incompatible with the episode context, return null for every field —
do NOT force a match.

Search results:
{results_text}

Return ONLY valid JSON with these fields (use null if not found):
{{
  "full_name": "their full real name (not a descriptor like 'The Cancer Doctor')",
  "bio": "2-3 sentence bio",
  "expertise": ["field1", "field2"],
  "credentials": "PhD, MD, CEO of X, Professor at Y, etc.",
  "notable_for": "what they're most known for, one sentence",
  "social_links": {{"twitter": "url or null", "linkedin": "url or null", "website": "url or null"}},
  "photo_url": "url or null"
}}"""


def _single_llm_attempt(prompt: str, temperature: float) -> tuple[dict | None, int, str | None, int]:
    """One HTTP round-trip. Returns (payload, status_code, error, duration_ms)."""
    t0 = time.monotonic()
    body = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": temperature,
        # Groq's gpt-oss-20b sometimes emits unsolicited tool calls and then
        # crashes with 400 "Tool choice is none, but model called a tool".
        # Declaring an empty tools list + explicit tool_choice=none suppresses
        # the hallucinated call path entirely.
        "tools": [],
        "tool_choice": "none",
    }
    if LLM_PROVIDER == "openrouter":
        # OpenRouter only returns authoritative per-request cost when asked
        body["usage"] = {"include": True}
    payload: dict | None = None
    status_code = 0
    error: str | None = None
    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json=body,
            timeout=300,
        )
        status_code = resp.status_code
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if status_code != 200:
            error = (payload or {}).get("error", {}).get("message") if isinstance(payload, dict) else resp.text[:500]
    except Exception as e:
        error = str(e)[:500]
    return payload, status_code, error, int((time.monotonic() - t0) * 1000)


def _llm_call_logged(prompt: str, *, temperature: float = 0.3) -> str | None:
    """Direct HTTP LLM call with per-request usage logging. Returns text or None.

    Retries once on 400 to paper over Groq's intermittent tool-call
    hallucinations — every attempt still gets its own llm_usage row so the
    retry cost is visible.
    """
    payload, status_code, error, duration_ms = _single_llm_attempt(prompt, temperature)
    attempts = [(payload, status_code, error, duration_ms)]
    if status_code == 400:
        payload, status_code, error, duration_ms = _single_llm_attempt(prompt, temperature)
        attempts.append((payload, status_code, error, duration_ms))

    for attempt_payload, attempt_status, attempt_error, attempt_dur in attempts:
        with _DB_LOCK:
            log_llm_call(
                episode_id=None,  # stage0 is per-person, not per-episode
                stage=STAGE,
                provider=LLM_PROVIDER,
                model=LLM_MODEL,
                status_code=attempt_status,
                payload=attempt_payload,
                duration_ms=attempt_dur,
                error=attempt_error,
            )

    if status_code != 200 or not payload:
        return None
    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None


_TITLE_STRIP = re.compile(r"[|•\-–—:()\[\]]")
_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "with", "and", "or",
    "my", "his", "her", "their", "our", "is", "how", "why", "what", "when",
    "about", "from", "at", "by", "as", "be", "this", "that", "ep", "e",
}


def _discriminative_terms(name: str, episode_title: str) -> str:
    """Extract the part of the episode title that disambiguates the guest.

    Drops the guest's own name + generic words + episode codes, keeps the
    distinctive phrase (brand, role, claim to fame). This goes into the
    SearXNG query so "Holly Tucker NotOnTheHighStreet" beats the country singer.
    """
    if not episode_title:
        return ""
    name_tokens = {t.lower() for t in name.split() if t}
    cleaned = _TITLE_STRIP.sub(" ", episode_title)
    keep = []
    for tok in cleaned.split():
        low = tok.lower()
        if low in name_tokens or low in _STOPWORDS:
            continue
        if re.fullmatch(r"e\d+|ep\d+|\d+", low):
            continue
        if len(tok) < 3:
            continue
        keep.append(tok)
        if len(keep) >= 6:
            break
    return " ".join(keep)


def search_guest(
    name: str,
    episode_title: str = "",
    person_id: str | None = None,
) -> tuple[list[dict], str]:
    """Search for a guest using SearXNG. Returns (results, query_used).

    When ``episode_title`` is provided the query is prefixed with discriminative
    terms pulled from it — kills the "Holly Tucker matched to country singer"
    disambiguation failure. Falls back progressively to looser queries if the
    context-rich one returns nothing.
    """
    context = _discriminative_terms(name, episode_title)
    queries = []
    if context:
        queries.append(f'"{name}" {context}')
    queries.append(f'"{name}" podcast OR author OR expert OR entrepreneur')
    queries.append(name)

    for query in queries:
        results = searxng_search(
            query,
            engines="duckduckgo,wikipedia",
            max_results=5,
            stage=STAGE, person_id=person_id,
        )
        if results:
            return results, query
    return [], queries[-1]


def structure_profile(
    name: str,
    search_results: list[dict],
    episode_title: str = "",
    episode_description: str = "",
) -> dict | None:
    """Use LLM to structure search results into a guest profile.

    ``episode_title`` / ``episode_description`` are passed to the LLM so it can
    reject search results that describe a different person with the same name.
    """
    if not search_results:
        return None

    results_text = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nContent: {r.get('content', '')}"
        for r in search_results
    )
    text = _llm_call_logged(PROFILE_PROMPT.format(
        name=name,
        episode_title=episode_title or "(unknown)",
        episode_description=(episode_description or "")[:500] or "(none)",
        results_text=results_text,
    ))
    if not text:
        return None

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _build_sources(results: list[dict], query: str) -> list[dict]:
    """Project SearXNG results into the shape stored on people.sources."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "url": r.get("url") or "",
            "title": (r.get("title") or "").strip(),
            "snippet": (r.get("content") or "").strip()[:300],
            "fetched_at": fetched_at,
            "query": query,
        }
        for r in results
        if r.get("url")
    ]


def enrich_guests(
    limit: int = 0,
    dry_run: bool = False,
    youtube_ids: list[str] | None = None,
):
    """Enrich unenriched guests with web search profiles.

    If ``youtube_ids`` is provided, only considers guests from those episodes —
    used by the pipeline runner to scope stage0 to a specific batch.
    """
    if youtube_ids:
        eps = fetch_all(
            "SELECT guest_names, title, description FROM episodes "
            "WHERE guest_names IS NOT NULL AND youtube_id = ANY(%s)",
            (list(youtube_ids),),
        )
    else:
        eps = fetch_all(
            "SELECT guest_names, title, description FROM episodes "
            "WHERE guest_names IS NOT NULL"
        )
    # Pick one representative episode per guest name so the search + profile
    # prompt can disambiguate between people who share a name.
    context_by_name: dict[str, tuple[str, str]] = {}
    all_names: set[str] = set()
    for ep in eps:
        title = ep.get("title") or ""
        description = ep.get("description") or ""
        for name in (ep.get("guest_names") or []):
            if not name or len(name) <= 2:
                continue
            all_names.add(name)
            context_by_name.setdefault(name, (title, description))

    if all_names:
        enriched = fetch_all(
            "SELECT name FROM people WHERE enriched_at IS NOT NULL AND name = ANY(%s)",
            (list(all_names),),
        )
    else:
        enriched = []
    enriched_names = {p["name"] for p in enriched}

    to_enrich = sorted(all_names - enriched_names)
    if limit:
        to_enrich = to_enrich[:limit]

    print(f"Guests to enrich: {len(to_enrich)} (of {len(all_names)} unique, {len(enriched_names)} already done)")
    print(f"{'#':<4} {'Name':<30} {'Status':<10} {'Bio':<50}")
    print("-" * 100)

    enriched_count = 0
    failed_count = 0

    def _fetch(name: str):
        """Worker: search + LLM profile for one guest. DB-free so it runs in threads."""
        ep_title, ep_desc = context_by_name.get(name, ("", ""))
        results, query = search_guest(name, episode_title=ep_title)
        if not results:
            return name, "no-results", None, None, None, None
        try:
            profile = structure_profile(
                name, results,
                episode_title=ep_title,
                episode_description=ep_desc,
            )
        except Exception as e:
            return name, "error", None, None, None, str(e)[:50]
        if not profile:
            return name, "llm-fail", None, None, None, None
        return name, "ok", profile, results, query, None

    idx_by_name = {name: i for i, name in enumerate(to_enrich, 1)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_fetch, name) for name in to_enrich]
        for future in as_completed(futures):
            name, status, profile, results, query, err = future.result()
            i = idx_by_name[name]

            if status == "no-results":
                print(f"{i:<4} {name:<30} {'no-results':<10}")
                failed_count += 1
                continue
            if status == "error":
                print(f"{i:<4} {name:<30} {'error':<10} {err}")
                failed_count += 1
                continue
            if status == "llm-fail":
                print(f"{i:<4} {name:<30} {'llm-fail':<10}")
                failed_count += 1
                continue

            full_name = profile.get("full_name") or name
            bio = (profile.get("bio") or "")[:200]
            print(f"{i:<4} {name:<30} {'ok':<10} {bio[:50]}")

            if not dry_run:
                from scripts.agents.stage1_prep import get_or_create_person
                person = get_or_create_person(full_name)

                # db.py globally adapts list→Json, which collides with text[] columns.
                # Build expertise as a literal ARRAY[...]::text[] fragment; other
                # fields flow through regular %s params.
                update_data = {
                    "enriched_at": datetime.now(timezone.utc).isoformat()
                }
                if profile.get("bio"):
                    update_data["bio"] = profile["bio"]
                if profile.get("credentials"):
                    update_data["credentials"] = profile["credentials"]
                if profile.get("notable_for"):
                    update_data["notable_for"] = profile["notable_for"]
                if profile.get("social_links"):
                    update_data["social_links"] = profile["social_links"]
                if profile.get("photo_url"):
                    update_data["photo_url"] = profile["photo_url"]
                # Stash the raw search URLs as references for the wiki page
                update_data["sources"] = json.dumps(_build_sources(results, query))

                if full_name != name and full_name != person["name"]:
                    update_data["name"] = full_name

                cols = list(update_data.keys())
                set_parts = [f"{c}=%s" for c in cols]
                params = [update_data[c] for c in cols]

                expertise = profile.get("expertise") or []
                if isinstance(expertise, list) and expertise:
                    placeholders = ",".join(["%s"] * len(expertise))
                    set_parts.append(f"expertise=ARRAY[{placeholders}]::text[]")
                    params.extend(str(x) for x in expertise)

                params.append(person["id"])
                execute(
                    f"UPDATE people SET {', '.join(set_parts)} WHERE id=%s",
                    params,
                )

            enriched_count += 1

    print(f"\n{'=' * 60}")
    print(f"Enriched: {enriched_count}, Failed: {failed_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich guest profiles via web search")
    parser.add_argument("--limit", type=int, default=0, help="Limit guests to enrich")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    parser.add_argument(
        "--youtube-ids", default="",
        help="Comma-separated list of youtube_ids to scope enrichment to",
    )
    args = parser.parse_args()

    yids = [y for y in args.youtube_ids.split(",") if y] or None
    enrich_guests(limit=args.limit, dry_run=args.dry_run, youtube_ids=yids)
