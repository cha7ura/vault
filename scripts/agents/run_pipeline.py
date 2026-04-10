"""Pipeline runner — orchestrates PREP → CLEAN → EXTRACT+ENRICH."""
from __future__ import annotations

import argparse
import asyncio
import time

from scripts.agents.config import DOAC_CHANNEL_SLUG, WIKI_DIR
from scripts.agents.db import fetch_all, fetch_one
from scripts.agents.stage1_prep import prep_episode
from scripts.agents.stage2_clean import clean_episode
from scripts.agents.stage3_extract import extract_episode
from scripts.agents.stage3_enrich import run_enrichment


def get_episodes(channel_slug: str) -> list[dict]:
    """Fetch episodes ordered oldest → newest (chronological wiki accumulation)."""
    channel = fetch_one("SELECT id FROM channels WHERE slug=%s", (channel_slug,))
    if not channel:
        raise ValueError(f"Channel not found: {channel_slug}")
    return fetch_all(
        """
        SELECT id, youtube_id, title, published_at, duration_seconds,
               intro_end_position, knowledge_processed_at, wiki_processed_at, speaker_map
        FROM episodes
        WHERE channel_id=%s
        ORDER BY published_at NULLS LAST
        """,
        (channel["id"],),
    )


def seed_wiki() -> None:
    """Ensure seed pages exist before processing any episodes.
    No-op if wiki/_index.md already has the seed entries.
    """
    from scripts.agents.wiki_writer import read_index
    index = read_index(WIKI_DIR)
    if "steven bartlett" in index and "diary of a ceo" in index:
        print("  Wiki already seeded — skipping")
        return
    print("  Wiki seed pages missing — please run Task 2 (create wiki/ directory) first")


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
    """Run Stage 3 WIKI EXTRACT for all episodes, oldest → newest."""
    print(f"\n{'='*60}")
    print(f"STAGE 3 — WIKI EXTRACT ({len(episodes)} episodes)")
    print(f"{'='*60}\n")

    # Ensure seed pages exist before processing
    seed_wiki()

    for idx, ep in enumerate(episodes, 1):
        if ep.get("wiki_processed_at"):
            print(f"[{idx}/{len(episodes)}] SKIP — wiki already processed")
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
        if not prep_results:
            print("Loading speaker maps from DB...")
            for ep in episodes:
                prep_results[ep["id"]] = {
                    "episode_id": ep["id"],
                    "intro_end_position": ep.get("intro_end_position", 0),
                    "speakers": ep.get("speaker_map") or {},
                }
        run_stage3(episodes, prep_results, channel_slug=args.channel)

    if args.stage in ("enrich", "all"):
        run_enrichment()

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
