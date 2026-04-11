"""One-off: A/B the episode summary model. Reuses existing wiki entity
pages so we don't re-run Groq extraction — only the summary call differs.
Writes both outputs to /tmp for side-by-side diffing."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from scripts.agents import wiki_extract
from scripts.agents.config import WIKI_DIR
from scripts.agents.db import fetch_one, fetch_all
from scripts.agents.wiki_extract import write_episode_summary


def collect_touched_pages(youtube_id: str, wiki_dir: Path) -> list[str]:
    """Find all entity pages that mention this youtube_id in their edges
    or observations (crude grep — the episode id lives in frontmatter YAML)."""
    matches: list[Path] = []
    for p in wiki_dir.rglob("*.md"):
        if p.parent.name == "_episodes":
            continue
        if youtube_id in p.read_text(encoding="utf-8"):
            matches.append(p)
    return [p.read_text(encoding="utf-8") for p in matches]


def run_one(model: str, youtube_id: str, episode: dict, pages: list[str], label: str) -> Path:
    wiki_extract.WIKI_SUMMARY_MODEL = model
    print(f"\n=== {label}: {model} ===")
    write_episode_summary(
        episode=episode,
        touched_page_texts=pages,
        wiki_dir=WIKI_DIR,
    )
    out_path = WIKI_DIR / "_episodes" / f"{youtube_id}.md"
    copy = Path(f"/tmp/summary_{label}.md")
    shutil.copy(out_path, copy)
    print(f"  saved → {copy}")
    return copy


def main():
    youtube_id = sys.argv[1] if len(sys.argv) > 1 else "j1i4WkJ4qFo"
    ep = fetch_one(
        "SELECT id, youtube_id, title, published_at FROM episodes WHERE youtube_id=%s",
        (youtube_id,),
    )
    if not ep:
        sys.exit(f"episode not found: {youtube_id}")

    pages = collect_touched_pages(youtube_id, WIKI_DIR)
    print(f"touched pages for {youtube_id}: {len(pages)}")

    episode = {
        "episode_id": ep["id"],
        "youtube_id": ep["youtube_id"],
        "title": ep["title"],
        "published_at": str(ep["published_at"]),
        "guest_name": "",
    }

    # Back up the currently-live summary so we can restore it at the end
    live_path = WIKI_DIR / "_episodes" / f"{youtube_id}.md"
    backup = live_path.read_text(encoding="utf-8")

    run_one("z-ai/glm-5.1", youtube_id, episode, pages, "glm")
    run_one("google/gemini-2.5-flash", youtube_id, episode, pages, "gemini")

    # Restore the live page (don't leave it as whichever ran last)
    live_path.write_text(backup, encoding="utf-8")
    print(f"\n  restored live summary → {live_path}")

    # Cost comparison
    rows = fetch_all(
        """
        SELECT model, cost_usd::float cost, prompt_tokens, completion_tokens,
               reasoning_tokens, duration_ms
        FROM llm_usage
        WHERE episode_id=%s AND stage='wiki_summary'
        ORDER BY created_at DESC LIMIT 2
        """,
        (ep["id"],),
    )
    print("\n=== cost comparison ===")
    for r in rows:
        print(
            f"  {r['model']:30} ${r['cost']:.6f}  "
            f"in={r['prompt_tokens']:5d} out={r['completion_tokens']:5d} "
            f"reasoning={r['reasoning_tokens']:5d}  {r['duration_ms']}ms"
        )


if __name__ == "__main__":
    main()
