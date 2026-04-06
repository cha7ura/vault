"""Pipeline runner — orchestrates PREP → CLEAN → EXTRACT+ENRICH."""
from __future__ import annotations

import argparse
import asyncio
import time

from scripts.agents.config import get_supabase, DOAC_CHANNEL_SLUG
from scripts.agents.stage1_prep import prep_episode
from scripts.agents.stage2_clean import clean_episode
from scripts.agents.stage3_extract import extract_episode, seed_host_and_podcast
from scripts.agents.stage3_enrich import run_enrichment


def get_episodes(channel_slug: str) -> list[dict]:
    """Fetch episodes that have segments (diarized)."""
    sb = get_supabase()

    # Get channel
    channel = (
        sb.table("channels")
        .select("id")
        .eq("slug", channel_slug)
        .single()
        .execute()
    ).data

    # Get episodes ordered by duration (short first)
    episodes = (
        sb.table("episodes")
        .select("id, youtube_id, title, published_at, duration_seconds, "
                "intro_end_position, knowledge_processed_at")
        .eq("channel_id", channel["id"])
        .order("duration_seconds")
        .execute()
    ).data

    return episodes


def run_stage1(episodes: list[dict]) -> dict:
    """Run Stage 1 PREP for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 1 — PREP ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    results = {}
    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {(ep.get('title') or '')[:50]}")
        t_start = time.time()
        result = prep_episode(ep["id"])
        elapsed = time.time() - t_start
        results[ep["id"]] = result
        speakers = ", ".join(
            f"{v['name']} ({v['role']})" for v in result["speakers"].values()
        )
        print(f"    Intro ends at segment {result['intro_end_position']}, "
              f"speakers: {speakers} ({elapsed:.1f}s)")

    return results


def run_stage2(episodes: list[dict], prep_results: dict):
    """Run Stage 2 CLEAN for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 2 — CLEAN ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    for idx, ep in enumerate(episodes, 1):
        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {(ep.get('title') or '')[:50]}")
        prep = prep_results.get(ep["id"])
        if not prep:
            print(f"    SKIP — no prep result")
            continue
        t_start = time.time()
        stats = clean_episode(ep["id"], prep)
        elapsed = time.time() - t_start
        print(f"    {stats['total_segments']} segments, {stats['flagged_for_review']} flagged, "
              f"{stats['quality_issues']} issues ({elapsed:.1f}s)")


def run_stage3(episodes: list[dict], prep_results: dict, channel_slug: str = DOAC_CHANNEL_SLUG):
    """Run Stage 3 EXTRACT for all episodes."""
    print(f"\n{'='*60}")
    print(f"STAGE 3 — EXTRACT ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    # Seed host + podcast entities once before first episode
    if channel_slug == DOAC_CHANNEL_SLUG:
        earliest_date = None
        for ep in episodes:
            pa = ep.get("published_at")
            if pa and (not earliest_date or pa < earliest_date):
                earliest_date = pa
        print("Seeding host + podcast profile...")
        asyncio.run(seed_host_and_podcast(
            host_name="Steven Bartlett",
            host_bio="Entrepreneur, investor, author of Happy Sexy Millionaire, "
                     "CEO of Flight Story, former CEO of Social Chain. "
                     "Investor in Huel, sits on the board of Huel.",
            podcast_name="Diary of a CEO",
            podcast_description="The Diary of a CEO is a podcast hosted by Steven Bartlett "
                                "featuring interviews with world-class guests on business, "
                                "health, relationships, and personal development.",
            first_episode_date=earliest_date,
        ))

    for idx, ep in enumerate(episodes, 1):
        if ep.get("knowledge_processed_at"):
            print(f"[{idx}/{len(episodes)}] SKIP — already processed")
            continue

        print(f"[{idx}/{len(episodes)}] {ep['youtube_id']} — {(ep.get('title') or '')[:50]}")
        prep = prep_results.get(ep["id"])
        speaker_map = prep["speakers"] if prep else {}

        t_start = time.time()
        stats = asyncio.run(extract_episode(ep["id"], speaker_map))
        elapsed = time.time() - t_start
        print(f"    {stats['substantive_turns']}/{stats['total_turns']} substantive, "
              f"{stats['show_note_links']} links ({elapsed:.1f}s)")


def main():
    parser = argparse.ArgumentParser(description="Podcast Vault Pipeline Runner")
    parser.add_argument(
        "--channel", default=DOAC_CHANNEL_SLUG,
        help=f"Channel slug (default: {DOAC_CHANNEL_SLUG})",
    )
    parser.add_argument(
        "--stage",
        choices=["prep", "clean", "extract", "enrich", "all"],
        default="all",
        help="Which stage to run (default: all)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit number of episodes to process (0 = all)",
    )
    args = parser.parse_args()

    episodes = get_episodes(args.channel)
    if args.limit > 0:
        episodes = episodes[:args.limit]

    print(f"Pipeline: {args.stage} | Channel: {args.channel} | Episodes: {len(episodes)}")

    prep_results = {}

    if args.stage in ("prep", "all"):
        prep_results = run_stage1(episodes)

    if args.stage in ("clean", "all"):
        if not prep_results:
            # Load prep results from DB (intro_end_position already saved)
            print("Loading prep results from DB...")
            for ep in episodes:
                prep_results[ep["id"]] = {
                    "episode_id": ep["id"],
                    "intro_end_position": ep.get("intro_end_position", 0),
                    "speakers": {},
                }
        run_stage2(episodes, prep_results)

    if args.stage in ("extract", "all"):
        run_stage3(episodes, prep_results, channel_slug=args.channel)

    if args.stage in ("enrich", "all"):
        run_enrichment()

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
