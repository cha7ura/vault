#!/usr/bin/env python3
"""
Stage 3 — Build agent memory with LLM triage and merge.

Processes transcript segments for each mapped person, uses LLM to triage
filler vs substantive turns, and incrementally builds a structured memory
for each person.

Usage:
    # Process all mapped people for a channel
    python scripts/agents/build_memory.py --channel my-channel

    # Process a single person
    python scripts/agents/build_memory.py --channel my-channel --person-slug john-doe

    # Resume from last checkpoint
    python scripts/agents/build_memory.py --channel my-channel --resume
"""

import argparse
import copy
import json
import re
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import requests

# Allow running as `python scripts/agents/build_memory.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    get_supabase,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    FILLER_MAX_WORDS,
    FILLER_PHRASES,
    CONTEXT_WINDOW_TURNS,
)
from prompts import (
    EMPTY_MEMORY,
    TRIAGE_PROMPT,
    MEMORY_MERGE_PROMPT,
    EPISODE_SUMMARY_PROMPT,
)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def llm_call(prompt: str, temperature: float = 0.3) -> str:
    """Send a prompt to Ollama and return the response text."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def parse_json_response(text: str) -> dict | None:
    """Parse a JSON response, stripping markdown fencing if present."""
    cleaned = text.strip()
    # Strip ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Filler detection
# ---------------------------------------------------------------------------

def is_filler_fast(text: str) -> bool:
    """Heuristic filler check: short turn with known filler phrase."""
    words = text.split()
    if len(words) > FILLER_MAX_WORDS:
        return False
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return cleaned in FILLER_PHRASES


def is_filler_llm(text: str) -> bool:
    """Use LLM triage for borderline cases (around 10 words)."""
    prompt = TRIAGE_PROMPT.format(text=text)
    response = llm_call(prompt, temperature=0.1)
    return response.upper().startswith("FILLER")


# ---------------------------------------------------------------------------
# Memory operations
# ---------------------------------------------------------------------------

def merge_memory(
    person_name: str,
    current_memory: dict,
    context_turns: list[str],
    new_turn: str,
    episode_id: str,
    episode_date: str,
    role: str,
) -> dict:
    """Call LLM to merge new turn info into existing memory."""
    prompt = MEMORY_MERGE_PROMPT.format(
        person_name=person_name,
        current_memory=json.dumps(current_memory, indent=2),
        context_turns="\n".join(context_turns),
        new_turn=new_turn,
        episode_id=episode_id,
        episode_date=episode_date,
        role=role,
    )
    response = llm_call(prompt)
    updated = parse_json_response(response)
    if updated is None:
        print("    [warn] JSON parse failed on merge response, keeping previous memory")
        return current_memory
    return updated


def generate_episode_summary(
    person_name: str,
    episode_id: str,
    episode_date: str,
    turns: list[str],
) -> dict | None:
    """Generate an episode summary for a person's contributions."""
    prompt = EPISODE_SUMMARY_PROMPT.format(
        person_name=person_name,
        episode_id=episode_id,
        episode_date=episode_date,
        turns="\n".join(f"- {t}" for t in turns),
    )
    response = llm_call(prompt)
    return parse_json_response(response)


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_person(
    sb,
    person_id: str,
    person_name: str,
    channel_id: str,
    resume: bool = False,
) -> None:
    """Main loop: build memory for a single person across all their episodes."""

    # 1. Load or create agent_memories row
    mem_rows = (
        sb.table("agent_memories")
        .select("*")
        .eq("person_id", person_id)
        .eq("channel_id", channel_id)
        .limit(1)
        .execute()
    ).data

    if mem_rows:
        mem_row = mem_rows[0]
        memory = mem_row["memory"] or copy.deepcopy(EMPTY_MEMORY)
        last_episode_id = mem_row.get("last_episode_id")
        last_position = mem_row.get("last_position", 0)
        turns_processed = mem_row.get("turns_processed", 0)
        memory_version = mem_row.get("memory_version", 0)
    else:
        # Create new row
        now = datetime.now(timezone.utc).isoformat()
        insert_data = {
            "person_id": person_id,
            "channel_id": channel_id,
            "memory": copy.deepcopy(EMPTY_MEMORY),
            "last_episode_id": None,
            "last_position": 0,
            "turns_processed": 0,
            "memory_version": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = sb.table("agent_memories").insert(insert_data).execute()
        mem_row = result.data[0]
        memory = copy.deepcopy(EMPTY_MEMORY)
        last_episode_id = None
        last_position = 0
        turns_processed = 0
        memory_version = 0

    mem_id = mem_row["id"]

    # 2. Get episodes where person has mapped speaker_embeddings
    episode_rows = (
        sb.table("speaker_embeddings")
        .select("episode_id, episodes(id, youtube_id, title, published_at)")
        .eq("person_id", person_id)
        .execute()
    ).data

    if not episode_rows:
        print(f"  No mapped episodes for {person_name}")
        return

    # Deduplicate and sort by published_at ASC
    episodes_map = {}
    for row in episode_rows:
        ep = row["episodes"]
        episodes_map[ep["id"]] = ep
    episodes = sorted(episodes_map.values(), key=lambda e: e["published_at"])

    # 3. If resume, skip to last checkpoint
    start_ep_idx = 0
    start_position = 0
    if resume and last_episode_id:
        for i, ep in enumerate(episodes):
            if ep["id"] == last_episode_id:
                start_ep_idx = i
                start_position = last_position + 1
                break
        print(f"  Resuming from episode {start_ep_idx + 1}/{len(episodes)}, position {start_position}")

    total_eps = len(episodes)

    # 4. Process each episode
    for ep_idx in range(start_ep_idx, total_eps):
        ep = episodes[ep_idx]
        ep_id = ep["id"]
        ep_date = ep["published_at"] or ""
        print(f"  [{ep_idx + 1}/{total_eps}] {ep['youtube_id']} — {ep['title']}")

        # Get person's speaker labels for this episode
        person_embs = (
            sb.table("speaker_embeddings")
            .select("speaker_label")
            .eq("episode_id", ep_id)
            .eq("person_id", person_id)
            .execute()
        ).data
        person_labels = {e["speaker_label"] for e in person_embs}

        # Determine role (host appears in most episodes)
        role = "participant"
        host_check = (
            sb.table("speaker_embeddings")
            .select("person_id", count="exact")
            .eq("person_id", person_id)
            .execute()
        )
        total_appearances = host_check.count or 0
        if total_appearances > total_eps * 0.5:
            role = "host"

        # Load ALL segments for this episode (need context)
        segments = (
            sb.table("segments")
            .select("position, speaker, text")
            .eq("episode_id", ep_id)
            .order("position", desc=False)
            .execute()
        ).data

        if not segments:
            continue

        context_window: deque[str] = deque(maxlen=CONTEXT_WINDOW_TURNS)
        person_turns_this_ep: list[str] = []
        ep_turns_processed = 0

        for seg in segments:
            pos = seg["position"]

            # If resuming within this episode, skip already-processed positions
            if ep_idx == start_ep_idx and pos <= start_position and resume:
                context_window.append(f"[{seg['speaker']}] {seg['text']}")
                continue

            # Add every turn to context window
            turn_str = f"[{seg['speaker']}] {seg['text']}"
            context_window.append(turn_str)

            # Only process this person's turns
            if seg["speaker"] not in person_labels:
                continue

            text = seg["text"].strip()
            if not text:
                continue

            # Fast filler check
            if is_filler_fast(text):
                turns_processed += 1
                ep_turns_processed += 1
                continue

            # Borderline check: use LLM for turns around 10 words
            word_count = len(text.split())
            if word_count <= 10:
                if is_filler_llm(text):
                    turns_processed += 1
                    ep_turns_processed += 1
                    continue

            # Substantive turn — merge into memory
            person_turns_this_ep.append(text)
            memory = merge_memory(
                person_name=person_name,
                current_memory=memory,
                context_turns=list(context_window),
                new_turn=text,
                episode_id=ep_id,
                episode_date=ep_date,
                role=role,
            )
            turns_processed += 1
            ep_turns_processed += 1

            # Checkpoint every 10 turns
            if ep_turns_processed % 10 == 0:
                now = datetime.now(timezone.utc).isoformat()
                sb.table("agent_memories").update({
                    "memory": memory,
                    "last_episode_id": ep_id,
                    "last_position": pos,
                    "turns_processed": turns_processed,
                    "updated_at": now,
                }).eq("id", mem_id).execute()

            # Print progress every 50 turns
            if ep_turns_processed % 50 == 0:
                print(f"    ...{ep_turns_processed} turns processed in this episode")

        # 5. After each episode: generate summary and save
        if person_turns_this_ep:
            summary = generate_episode_summary(
                person_name=person_name,
                episode_id=ep_id,
                episode_date=ep_date,
                turns=person_turns_this_ep,
            )
            if summary:
                summary["episode_id"] = ep_id
                summary["episode_date"] = ep_date
                if "episodic_memory" not in memory:
                    memory["episodic_memory"] = []
                memory["episodic_memory"].append(summary)

        # 6. Save checkpoint after episode
        memory_version += 1
        now = datetime.now(timezone.utc).isoformat()
        sb.table("agent_memories").update({
            "memory": memory,
            "last_episode_id": ep_id,
            "last_position": segments[-1]["position"] if segments else 0,
            "turns_processed": turns_processed,
            "memory_version": memory_version,
            "updated_at": now,
        }).eq("id", mem_id).execute()

        print(f"    ✓ {len(person_turns_this_ep)} substantive turns, version {memory_version}")

    print(f"  Done — {turns_processed} total turns processed, memory version {memory_version}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 3: build agent memory with LLM triage and merge",
    )
    parser.add_argument(
        "--channel", type=str, required=True,
        help="Channel slug (e.g. 'my-channel')",
    )
    parser.add_argument(
        "--person-slug", type=str, default=None,
        help="Process a single person by slug (optional)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint",
    )
    args = parser.parse_args()

    # Check Ollama is running
    try:
        tags_resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        tags_resp.raise_for_status()
        available_models = [m["name"] for m in tags_resp.json().get("models", [])]
        if OLLAMA_MODEL not in available_models:
            print(f"Error: model '{OLLAMA_MODEL}' not found in Ollama.")
            print(f"Available models: {', '.join(available_models)}")
            sys.exit(1)
        print(f"Ollama OK — using model {OLLAMA_MODEL}")
    except requests.ConnectionError:
        print(f"Error: cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print("Make sure Ollama is running: ollama serve")
        sys.exit(1)

    sb = get_supabase()

    # Resolve channel
    channel_rows = (
        sb.table("channels")
        .select("id, name")
        .eq("slug", args.channel)
        .execute()
    ).data
    if not channel_rows:
        print(f"Error: channel '{args.channel}' not found.")
        sys.exit(1)

    channel = channel_rows[0]
    channel_id = channel["id"]
    print(f"Channel: {channel['name']} ({channel_id})\n")

    # Get people with mapped embeddings for this channel
    # Find all episodes for this channel, then all speaker_embeddings with person_id
    episode_rows = (
        sb.table("episodes")
        .select("id")
        .eq("channel_id", channel_id)
        .execute()
    ).data
    if not episode_rows:
        print("No episodes found for this channel.")
        return

    episode_ids = [e["id"] for e in episode_rows]

    # Get distinct person_ids from speaker_embeddings
    people_set: dict[str, dict] = {}
    for ep_id in episode_ids:
        emb_rows = (
            sb.table("speaker_embeddings")
            .select("person_id, people(id, name, slug)")
            .eq("episode_id", ep_id)
            .not_.is_("person_id", "null")
            .execute()
        ).data
        for row in emb_rows:
            pid = row["person_id"]
            if pid not in people_set and row.get("people"):
                people_set[pid] = row["people"]

    if not people_set:
        print("No mapped people found. Run map_speakers.py first.")
        return

    # Filter to single person if specified
    if args.person_slug:
        filtered = {
            pid: p for pid, p in people_set.items()
            if p["slug"] == args.person_slug
        }
        if not filtered:
            print(f"Error: person with slug '{args.person_slug}' not found in mapped speakers.")
            sys.exit(1)
        people_set = filtered

    print(f"Processing {len(people_set)} people:\n")

    for person_id, person_info in people_set.items():
        print(f"--- {person_info['name']} ({person_info['slug']}) ---")
        process_person(
            sb,
            person_id=person_id,
            person_name=person_info["name"],
            channel_id=channel_id,
            resume=args.resume,
        )
        print()

    print("All done.")


if __name__ == "__main__":
    main()
