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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import get_supabase, HOST_SIMILARITY_THRESHOLD


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

def get_or_create_person(sb, name: str, photo_url: str | None = None) -> dict:
    """
    Find a person by slug, or create one. Returns the person row dict.
    """
    slug = slugify(name)
    rows = (
        sb.table("people")
        .select("*")
        .eq("slug", slug)
        .limit(1)
        .execute()
    ).data

    if rows:
        return rows[0]

    insert_data = {"name": name, "slug": slug}
    if photo_url:
        insert_data["photo_url"] = photo_url

    result = sb.table("people").insert(insert_data).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# Host anchor
# ---------------------------------------------------------------------------

def get_host_anchor(sb, channel_id: str) -> tuple[str | None, list[float] | None]:
    """
    Determine the host person_id and compute the anchor embedding as the
    average of all confirmed host embeddings for this channel.

    Returns (host_person_id, anchor_embedding) or (None, None) if no host
    has been mapped yet.
    """
    # Find which person_id appears most in speaker_embeddings for this channel's episodes
    episodes = (
        sb.table("episodes")
        .select("id")
        .eq("channel_id", channel_id)
        .execute()
    ).data
    if not episodes:
        return None, None

    episode_ids = [e["id"] for e in episodes]

    # Get all mapped speaker embeddings for these episodes
    all_mapped = []
    for ep_id in episode_ids:
        rows = (
            sb.table("speaker_embeddings")
            .select("person_id, embedding")
            .eq("episode_id", ep_id)
            .not_.is_("person_id", "null")
            .execute()
        ).data
        all_mapped.extend(rows)

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
        row["embedding"] for row in all_mapped
        if row["person_id"] == host_person_id
    ]
    anchor = np.mean(
        [np.asarray(e, dtype=np.float64) for e in host_embeddings], axis=0
    ).tolist()

    return host_person_id, anchor


# ---------------------------------------------------------------------------
# Bootstrap mode
# ---------------------------------------------------------------------------

def bootstrap_host(sb, channel_id: str, channel_name: str) -> tuple[str, list[float]]:
    """
    Interactive bootstrap: show early transcript turns, ask user which
    speaker is the host, create the person entry, map that embedding,
    and return (host_person_id, anchor_embedding).
    """
    # Get the earliest processed episode with embeddings
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at")
        .eq("channel_id", channel_id)
        .not_.is_("processed_at", "null")
        .order("published_at", desc=False)
        .execute()
    ).data

    if not episodes:
        print("Error: no processed episodes found for this channel.")
        sys.exit(1)

    # Find the first episode that has unmapped speaker embeddings
    bootstrap_ep = None
    embeddings_data = []
    for ep in episodes:
        emb_rows = (
            sb.table("speaker_embeddings")
            .select("id, speaker_label, embedding")
            .eq("episode_id", ep["id"])
            .execute()
        ).data
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
    segments = (
        sb.table("segments")
        .select("position, speaker, text")
        .eq("episode_id", ep_id)
        .order("position", desc=False)
        .limit(10)
        .execute()
    ).data

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
    person = get_or_create_person(sb, host_name)
    host_person_id = person["id"]
    print(f"\nHost person: {person['name']} (id={host_person_id})")

    # Map the host embedding
    host_emb_row = next(e for e in embeddings_data if e["speaker_label"] == host_label)
    sb.table("speaker_embeddings").update({
        "person_id": host_person_id,
        "mapped_confidence": 1.0,
    }).eq("id", host_emb_row["id"]).execute()

    anchor = host_emb_row["embedding"]
    print(f"Mapped {host_label} → {host_name} (confidence=1.0)")

    # If 2 speakers and 1 guest, map the guest too
    other_labels = [l for l in speaker_labels if l != host_label]
    if len(other_labels) == 1:
        guest_rows = (
            sb.table("episode_guests")
            .select("guest_id, guests(id, name, photo_url)")
            .eq("episode_id", ep_id)
            .execute()
        ).data
        if len(guest_rows) == 1:
            guest_info = guest_rows[0]["guests"]
            guest_person = get_or_create_person(
                sb, guest_info["name"], guest_info.get("photo_url")
            )
            other_emb = next(
                e for e in embeddings_data if e["speaker_label"] == other_labels[0]
            )
            sb.table("speaker_embeddings").update({
                "person_id": guest_person["id"],
                "mapped_confidence": 1.0,
            }).eq("id", other_emb["id"]).execute()

            # Link guest to person
            sb.table("guests").update({
                "person_id": guest_person["id"],
            }).eq("id", guest_info["id"]).execute()

            print(f"Mapped {other_labels[0]} → {guest_info['name']} (guest, confidence=1.0)")

    print("\nBootstrap complete.\n")
    return host_person_id, anchor


# ---------------------------------------------------------------------------
# Auto-map a single episode
# ---------------------------------------------------------------------------

def auto_map_episode(
    sb,
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
    emb_rows = (
        sb.table("speaker_embeddings")
        .select("id, speaker_label, embedding")
        .eq("episode_id", episode_id)
        .is_("person_id", "null")
        .execute()
    ).data

    if not emb_rows:
        return False

    # Compute similarity of each speaker to host anchor
    similarities = []
    for row in emb_rows:
        sim = cosine_similarity(row["embedding"], host_anchor)
        similarities.append((row, sim))

    # Sort by similarity descending — highest is most likely the host
    similarities.sort(key=lambda x: x[1], reverse=True)

    best_row, best_sim = similarities[0]
    mapped_any = False

    if best_sim >= HOST_SIMILARITY_THRESHOLD:
        # Map as host
        sb.table("speaker_embeddings").update({
            "person_id": host_person_id,
            "mapped_confidence": round(best_sim, 4),
        }).eq("id", best_row["id"]).execute()
        print(f"    host: {best_row['speaker_label']} (sim={best_sim:.4f})")
        mapped_any = True

        # For 2-speaker episodes with exactly 1 guest, map the other speaker
        remaining = [r for r, _ in similarities if r["id"] != best_row["id"]]
        if len(remaining) == 1:
            guest_rows = (
                sb.table("episode_guests")
                .select("guest_id, guests(id, name, photo_url)")
                .eq("episode_id", episode_id)
                .execute()
            ).data
            if len(guest_rows) == 1:
                guest_info = guest_rows[0]["guests"]
                guest_person = get_or_create_person(
                    sb, guest_info["name"], guest_info.get("photo_url")
                )
                other_row = remaining[0]
                other_sim = next(
                    s for r, s in similarities if r["id"] == other_row["id"]
                )
                sb.table("speaker_embeddings").update({
                    "person_id": guest_person["id"],
                    "mapped_confidence": round(1.0 - other_sim, 4),
                }).eq("id", other_row["id"]).execute()

                # Link guest to person
                sb.table("guests").update({
                    "person_id": guest_person["id"],
                }).eq("id", guest_info["id"]).execute()

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
    channel_name = channel["name"]
    print(f"Channel: {channel_name} ({channel_id})\n")

    if args.bootstrap:
        host_person_id, host_anchor = bootstrap_host(sb, channel_id, channel_name)
    else:
        host_person_id, host_anchor = get_host_anchor(sb, channel_id)
        if host_person_id is None:
            print("Error: no host anchor found. Run with --bootstrap first.")
            sys.exit(1)

    # Get all processed episodes in chronological order
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at")
        .eq("channel_id", channel_id)
        .not_.is_("processed_at", "null")
        .order("published_at", desc=False)
        .execute()
    ).data

    if not episodes:
        print("No processed episodes found.")
        return

    total = len(episodes)
    mapped = 0
    skipped = 0

    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{total}] {ep['youtube_id']} — {ep['title']}")
        was_mapped = auto_map_episode(sb, ep["id"], host_person_id, host_anchor, channel_id)
        if was_mapped:
            mapped += 1
        else:
            skipped += 1

        # Refresh host anchor periodically (every 10 mapped episodes)
        if was_mapped and mapped % 10 == 0:
            updated_pid, updated_anchor = get_host_anchor(sb, channel_id)
            if updated_anchor is not None:
                host_anchor = updated_anchor
                print(f"  [anchor refreshed with {mapped} confirmed host embeddings]")

    print(f"\nDone — {mapped} mapped, {skipped} skipped (of {total} episodes)")


if __name__ == "__main__":
    main()
