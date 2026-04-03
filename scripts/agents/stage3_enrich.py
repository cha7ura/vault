"""Stage 3 — ENRICH: Web search, profile hydration, persona extraction."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from scripts.agents.config import get_supabase
from scripts.agents.llm import llm_json_call
from scripts.agents.search import searxng_search
from scripts.agents.prompts import PROFILE_EXTRACTION_PROMPT, PERSONA_EXTRACTION_PROMPT


# ---------------------------------------------------------------------------
# Search query builders
# ---------------------------------------------------------------------------

def build_person_search_query(name: str, expertise: str | None = None) -> str:
    """Build a search query for a person."""
    query = f'"{name}"'
    if expertise:
        query += f" {expertise}"
    return query


def build_study_search_query(authors: str, topic: str) -> str:
    """Build a search query for a study."""
    return f'"{authors}" {topic} site:pubmed.ncbi.nlm.nih.gov OR site:scholar.google.com'


def build_book_search_query(title: str, author: str | None = None) -> str:
    """Build a search query for a book."""
    query = f'"{title}"'
    if author:
        query += f' "{author}"'
    query += " site:goodreads.com OR site:amazon.com"
    return query


# ---------------------------------------------------------------------------
# Profile extraction
# ---------------------------------------------------------------------------

def extract_profile_from_search(name: str, search_results: list[dict]) -> dict:
    """Use LLM to extract structured profile from search results."""
    results_text = "\n\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\nContent: {r.get('content', '')}"
        for r in search_results
    )

    prompt = PROFILE_EXTRACTION_PROMPT.format(
        name=name, results_text=results_text,
    )
    result = llm_json_call(prompt)
    return result or {}


# ---------------------------------------------------------------------------
# 3g. Profile Hydration
# ---------------------------------------------------------------------------

def hydrate_person(person_id: str, name: str) -> dict | None:
    """Search for a person and update their profile in Supabase."""
    sb = get_supabase()

    results = searxng_search(
        build_person_search_query(name),
        engines="google,wikipedia",
        max_results=5,
    )

    if not results:
        return None

    profile = extract_profile_from_search(name, results)
    if not profile:
        return None

    update = {"hydrated_at": datetime.now(timezone.utc).isoformat()}
    if profile.get("bio"):
        update["bio"] = profile["bio"]
    if profile.get("photo_url"):
        update["photo_url"] = profile["photo_url"]

    sb.table("people").update(update).eq("id", person_id).execute()
    return profile


# ---------------------------------------------------------------------------
# 3h. Persona Extraction
# ---------------------------------------------------------------------------

def extract_persona(person_id: str, name: str) -> dict | None:
    """Build a persona JSON from a person's recent substantive turns."""
    sb = get_supabase()

    # Get recent substantive segments for this person
    segments = (
        sb.table("segments")
        .select("clean_text, text")
        .eq("person_id", person_id)
        .not_.is_("clean_text", "null")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    ).data

    if not segments or len(segments) < 10:
        return None

    turns_text = "\n".join(
        f"- {seg.get('clean_text') or seg['text']}"
        for seg in segments[:50]
    )

    prompt = PERSONA_EXTRACTION_PROMPT.format(name=name, turns_text=turns_text)
    persona = llm_json_call(prompt)

    if persona:
        sb.table("people").update({
            "persona_json": persona,
        }).eq("id", person_id).execute()

    return persona


# ---------------------------------------------------------------------------
# Batch enrichment runner
# ---------------------------------------------------------------------------

def run_enrichment():
    """Run batch enrichment for all unenriched people."""
    sb = get_supabase()

    # Find people without hydration
    people = (
        sb.table("people")
        .select("id, name")
        .is_("hydrated_at", "null")
        .execute()
    ).data

    print(f"Found {len(people)} people to hydrate")

    for i, person in enumerate(people, 1):
        print(f"[{i}/{len(people)}] Hydrating {person['name']}...")
        profile = hydrate_person(person["id"], person["name"])
        if profile:
            print(f"    Bio: {profile.get('bio', 'N/A')[:80]}")
        else:
            print(f"    No results found")
        time.sleep(2)  # Rate limit SearXNG

    # Persona extraction for people with enough data
    people_with_data = (
        sb.table("people")
        .select("id, name, persona_json")
        .is_("persona_json", "null")
        .execute()
    ).data

    print(f"\nFound {len(people_with_data)} people for persona extraction")

    for i, person in enumerate(people_with_data, 1):
        print(f"[{i}/{len(people_with_data)}] Persona: {person['name']}...")
        persona = extract_persona(person["id"], person["name"])
        if persona:
            style = persona.get("communication_style", {})
            print(f"    Style: {style.get('tone', 'N/A')}")
        else:
            print(f"    Not enough data")
