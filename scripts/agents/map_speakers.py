#!/usr/bin/env python3
"""
Stage 2 — Map speaker embeddings to people via voice fingerprinting.

Compares per-episode speaker embeddings against a host anchor (rolling average)
to identify the host, then infers guests from episode_guests metadata.

Usage:
    # First run — interactive bootstrap to identify the host
    python scripts/agents/map_speakers.py --channel my-channel --bootstrap

    # Auto-map all episodes
    python scripts/agents/map_speakers.py --channel my-channel
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np

# Allow running as `python scripts/agents/map_speakers.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.agents.config import HOST_SIMILARITY_THRESHOLD
from scripts.agents.db import (
    fetch_all,
    fetch_one,
    execute,
    execute_returning,
    parse_vector,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    a_arr = np.asarray(a, dtype=np.float64)
    b_arr = np.asarray(b, dtype=np.float64)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# People helpers
# ---------------------------------------------------------------------------

def get_or_create_person(name: str, photo_url: str | None = None) -> dict:
    """
    Find a person by slug, or create one. Returns the person row dict.
    """
    slug = slugify(name)
    existing = fetch_one(
        "SELECT * FROM people WHERE slug=%s LIMIT 1", (slug,)
    )
    if existing:
        return existing

    if photo_url:
        return execute_returning(
            "INSERT INTO people (name, slug, photo_url) VALUES (%s, %s, %s) RETURNING *",
            (name, slug, photo_url),
        )
    return execute_returning(
        "INSERT INTO people (name, slug) VALUES (%s, %s) RETURNING *",
        (name, slug),
    )


# ---------------------------------------------------------------------------
# Host anchor
# ---------------------------------------------------------------------------

def get_host_anchor(channel_id: str) -> tuple[str | None, list[float] | None]:
    """
    Determine the host person_id and compute the anchor embedding as the
    average of all confirmed host embeddings for this channel.

    Returns (host_person_id, anchor_embedding) or (None, None) if no host
    has been mapped yet.
    """
    # One-shot JOIN: pull all mapped embeddings for every episode in the channel
    all_mapped = fetch_all(
        """
        SELECT se.person_id, se.embedding
        FROM speaker_embeddings se
        JOIN episodes e ON e.id = se.episode_id
        WHERE e.channel_id = %s AND se.person_id IS NOT NULL
        """,
        (channel_id,),
    )

    if not all_mapped:
        return None, None

    # Count appearances per person
    person_counts: dict[str, int] = {}
    for row in all_mapped:
        pid = row["person_id"]
        person_counts[pid] = person_counts.get(pid, 0) + 1

    # Host is the person who appears most
    host_person_id = max(person_counts, key=person_counts.get)

    # Compute anchor as average of all host embeddings
    host_embeddings = [
        parse_vector(row["embedding"]) for row in all_mapped
        if row["person_id"] == host_person_id
    ]
    anchor = np.mean(
        [np.asarray(e, dtype=np.float64) for e in host_embeddings], axis=0
    ).tolist()

    return host_person_id, anchor


# ---------------------------------------------------------------------------
# Bootstrap mode
# ---------------------------------------------------------------------------

def bootstrap_host(channel_id: str, channel_name: str) -> tuple[str, list[float]]:
    """
    Interactive bootstrap: show early transcript turns, ask user which
    speaker is the host, create the person entry, map that embedding,
    and return (host_person_id, anchor_embedding).
    """
    # Get the earliest processed episode with embeddings
    episodes = fetch_all(
        """
        SELECT id, youtube_id, title, published_at
        FROM episodes
        WHERE channel_id=%s AND processed_at IS NOT NULL
        ORDER BY published_at ASC
        """,
        (channel_id,),
    )

    if not episodes:
        print("Error: no processed episodes found for this channel.")
        sys.exit(1)

    # Find the first episode that has unmapped speaker embeddings
    bootstrap_ep = None
    embeddings_data = []
    for ep in episodes:
        emb_rows = fetch_all(
            """
            SELECT id, speaker_label, embedding
            FROM speaker_embeddings
            WHERE episode_id=%s
            """,
            (ep["id"],),
        )
        if emb_rows:
            bootstrap_ep = ep
            embeddings_data = emb_rows
            break

    if not bootstrap_ep:
        print("Error: no episodes with speaker embeddings found.")
        sys.exit(1)

    ep_id = bootstrap_ep["id"]
    print(f"\nBootstrap episode: {bootstrap_ep['youtube_id']} — {bootstrap_ep['title']}")
    print(f"Published: {bootstrap_ep['published_at']}\n")

    # Show first 10 transcript turns
    segments = fetch_all(
        """
        SELECT position, speaker, text
        FROM segments
        WHERE episode_id=%s
        ORDER BY position ASC
        LIMIT 10
        """,
        (ep_id,),
    )

    if not segments:
        print("Error: no transcript segments found for this episode.")
        sys.exit(1)

    print("--- First 10 transcript turns ---")
    for seg in segments:
        print(f"  [{seg['speaker']}] {seg['text'][:120]}")
    print("---\n")

    # Show which speakers have embeddings
    speaker_labels = sorted(set(e["speaker_label"] for e in embeddings_data))
    print(f"Speakers with embeddings: {', '.join(speaker_labels)}\n")

    # Ask user which speaker is the host
    host_label = input(f"Which speaker label is the host of '{channel_name}'? ").strip()
    if host_label not in speaker_labels:
        print(f"Error: '{host_label}' not found in speaker labels.")
        sys.exit(1)

    host_name = input("Enter the host's full name: ").strip()
    if not host_name:
        print("Error: host name cannot be empty.")
        sys.exit(1)

    # Create or find the person
    person = get_or_create_person(host_name)
    host_person_id = person["id"]
    print(f"\nHost person: {person['name']} (id={host_person_id})")

    # Map the host embedding
    host_emb_row = next(e for e in embeddings_data if e["speaker_label"] == host_label)
    execute(
        """
        UPDATE speaker_embeddings
        SET person_id=%s, mapped_confidence=%s
        WHERE id=%s
        """,
        (host_person_id, 1.0, host_emb_row["id"]),
    )

    anchor = parse_vector(host_emb_row["embedding"])
    print(f"Mapped {host_label} → {host_name} (confidence=1.0)")

    # If 2 speakers and 1 guest, map the guest too
    other_labels = [l for l in speaker_labels if l != host_label]
    if len(other_labels) == 1:
        guest_rows = fetch_all(
            """
            SELECT g.id, g.name, g.photo_url
            FROM episode_guests eg
            JOIN guests g ON g.id = eg.guest_id
            WHERE eg.episode_id=%s
            """,
            (ep_id,),
        )
        if len(guest_rows) == 1:
            guest_info = guest_rows[0]
            guest_person = get_or_create_person(
                guest_info["name"], guest_info.get("photo_url")
            )
            other_emb = next(
                e for e in embeddings_data if e["speaker_label"] == other_labels[0]
            )
            execute(
                """
                UPDATE speaker_embeddings
                SET person_id=%s, mapped_confidence=%s
                WHERE id=%s
                """,
                (guest_person["id"], 1.0, other_emb["id"]),
            )

            # Link guest to person
            execute(
                "UPDATE guests SET person_id=%s WHERE id=%s",
                (guest_person["id"], guest_info["id"]),
            )

            print(f"Mapped {other_labels[0]} → {guest_info['name']} (guest, confidence=1.0)")

    print("\nBootstrap complete.\n")
    return host_person_id, anchor


# ---------------------------------------------------------------------------
# Auto-map a single episode
# ---------------------------------------------------------------------------

def auto_map_episode(
    episode_id: str,
    host_person_id: str,
    host_anchor: list[float],
    channel_id: str,
) -> bool:
    """
    Map speakers in a single episode using cosine similarity against the
    host anchor. Returns True if any mapping was made.
    """
    # Get unmapped embeddings for this episode
    emb_rows = fetch_all(
        """
        SELECT id, speaker_label, embedding
        FROM speaker_embeddings
        WHERE episode_id=%s AND person_id IS NULL
        """,
        (episode_id,),
    )

    if not emb_rows:
        return False

    # Compute similarity of each speaker to host anchor
    similarities = []
    for row in emb_rows:
        vec = parse_vector(row["embedding"])
        sim = cosine_similarity(vec, host_anchor)
        similarities.append((row, sim))

    # Sort by similarity descending — highest is most likely the host
    similarities.sort(key=lambda x: x[1], reverse=True)

    best_row, best_sim = similarities[0]
    mapped_any = False

    if best_sim >= HOST_SIMILARITY_THRESHOLD:
        # Map as host
        execute(
            """
            UPDATE speaker_embeddings
            SET person_id=%s, mapped_confidence=%s
            WHERE id=%s
            """,
            (host_person_id, round(best_sim, 4), best_row["id"]),
        )
        print(f"    host: {best_row['speaker_label']} (sim={best_sim:.4f})")
        mapped_any = True

        # For 2-speaker episodes with exactly 1 guest, map the other speaker
        remaining = [r for r, _ in similarities if r["id"] != best_row["id"]]
        if len(remaining) == 1:
            guest_rows = fetch_all(
                """
                SELECT g.id, g.name, g.photo_url
                FROM episode_guests eg
                JOIN guests g ON g.id = eg.guest_id
                WHERE eg.episode_id=%s
                """,
                (episode_id,),
            )
            if len(guest_rows) == 1:
                guest_info = guest_rows[0]
                guest_person = get_or_create_person(
                    guest_info["name"], guest_info.get("photo_url")
                )
                other_row = remaining[0]
                other_sim = next(
                    s for r, s in similarities if r["id"] == other_row["id"]
                )
                execute(
                    """
                    UPDATE speaker_embeddings
                    SET person_id=%s, mapped_confidence=%s
                    WHERE id=%s
                    """,
                    (guest_person["id"], round(1.0 - other_sim, 4), other_row["id"]),
                )

                # Link guest to person
                execute(
                    "UPDATE guests SET person_id=%s WHERE id=%s",
                    (guest_person["id"], guest_info["id"]),
                )

                print(f"    guest: {other_row['speaker_label']} → {guest_info['name']}")
                mapped_any = True
    else:
        print(f"    [skip] best similarity {best_sim:.4f} below threshold {HOST_SIMILARITY_THRESHOLD}")

    return mapped_any


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 2: map speaker embeddings to people via voice fingerprinting",
    )
    parser.add_argument(
        "--channel", type=str, required=True,
        help="Channel slug (e.g. 'my-channel')",
    )
    parser.add_argument(
        "--bootstrap", action="store_true",
        help="Interactive first-run mode to identify the host",
    )
    args = parser.parse_args()

    # Resolve channel
    channel = fetch_one(
        "SELECT id, name FROM channels WHERE slug=%s",
        (args.channel,),
    )
    if not channel:
        print(f"Error: channel '{args.channel}' not found.")
        sys.exit(1)

    channel_id = channel["id"]
    channel_name = channel["name"]
    print(f"Channel: {channel_name} ({channel_id})\n")

    if args.bootstrap:
        host_person_id, host_anchor = bootstrap_host(channel_id, channel_name)
    else:
        host_person_id, host_anchor = get_host_anchor(channel_id)
        if host_person_id is None:
            print("Error: no host anchor found. Run with --bootstrap first.")
            sys.exit(1)

    # Get all processed episodes in chronological order
    episodes = fetch_all(
        """
        SELECT id, youtube_id, title, published_at
        FROM episodes
        WHERE channel_id=%s AND processed_at IS NOT NULL
        ORDER BY published_at ASC
        """,
        (channel_id,),
    )

    if not episodes:
        print("No processed episodes found.")
        return

    total = len(episodes)
    mapped = 0
    skipped = 0

    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{total}] {ep['youtube_id']} — {ep['title']}")
        was_mapped = auto_map_episode(ep["id"], host_person_id, host_anchor, channel_id)
        if was_mapped:
            mapped += 1
        else:
            skipped += 1

        # Refresh host anchor periodically (every 10 mapped episodes)
        if was_mapped and mapped % 10 == 0:
            updated_pid, updated_anchor = get_host_anchor(channel_id)
            if updated_anchor is not None:
                host_anchor = updated_anchor
                print(f"  [anchor refreshed with {mapped} confirmed host embeddings]")

    print(f"\nDone — {mapped} mapped, {skipped} skipped (of {total} episodes)")


if __name__ == "__main__":
    main()
