"""Stage 3 lint pass — deduplication, orphan detection, observation promotion."""
from __future__ import annotations

import re
from pathlib import Path

import Levenshtein

from scripts.agents.config import WIKI_DIR
from scripts.agents.wiki_writer import load_page, read_index

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _all_entity_pages(wiki_dir: Path) -> list[Path]:
    """Return all .md files under entity subdirectories (not _index or _episodes)."""
    pages = []
    for subdir in ["people", "concepts", "works", "methods", "organizations", "products", "podcasts"]:
        pages.extend((wiki_dir / subdir).glob("*.md"))
    return pages


def find_near_duplicates(wiki_dir: Path, threshold: float = 0.85) -> list[tuple[Path, Path, float]]:
    """Find pairs of entity pages with similar names using Levenshtein ratio.

    Returns list of (path1, path2, similarity_score) sorted by score desc.
    Only compares pages in the same subdirectory.
    """
    pages = _all_entity_pages(wiki_dir)
    names: dict[Path, str] = {}
    for p in pages:
        fm = load_page(p)
        if fm.get("name"):
            names[p] = fm["name"].lower()

    duplicates = []
    paths = list(names.keys())
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            p1, p2 = paths[i], paths[j]
            # Only compare pages of the same entity type (same subdirectory)
            if p1.parent != p2.parent:
                continue
            score = Levenshtein.ratio(names[p1], names[p2])
            if score >= threshold:
                duplicates.append((p1, p2, score))
    return sorted(duplicates, key=lambda x: x[2], reverse=True)


def find_orphan_wikilinks(wiki_dir: Path) -> list[str]:
    """Find wikilinks in entity pages that point to non-existent pages.

    Returns list of "source_page → target_link" strings.
    """
    orphans = []
    for p in _all_entity_pages(wiki_dir):
        text = p.read_text(encoding="utf-8")
        for match in WIKILINK_RE.finditer(text):
            link = match.group(1)
            # Handle "path|display" format
            link_path = link.split("|")[0]
            target = wiki_dir / f"{link_path}.md"
            if not target.exists():
                orphans.append(f"{p.relative_to(wiki_dir)} → [[{link}]]")
    return orphans


def promote_observations(wiki_dir: Path) -> int:
    """Scan all observations fields. If an observation text contains the name
    of an existing entity (index lookup), log it as a candidate for promotion.

    Returns count of promotable observations found (human reviews these — no auto-edit).
    """
    index = read_index(wiki_dir)
    index_names = set(index.keys())
    promotable = 0

    for p in _all_entity_pages(wiki_dir):
        fm = load_page(p)
        obs_list = fm.get("observations") or []
        for obs in obs_list:
            text = obs.get("text", "").lower()
            # Check if any known entity name appears in the observation text
            for known_name in index_names:
                if len(known_name) > 4 and known_name in text:
                    print(f"  PROMOTE CANDIDATE: {p.name} obs → mentions '{known_name}': {obs['text'][:80]}")
                    promotable += 1
                    break
    return promotable


def run_lint(wiki_dir: Path) -> None:
    """Run all lint checks and print report. Does not auto-merge (human review required)."""
    print(f"\n{'='*60}")
    print(f"WIKI LINT PASS — {wiki_dir}")
    print(f"{'='*60}\n")

    # 1. Near-duplicates
    print("Checking for near-duplicate pages...")
    dupes = find_near_duplicates(wiki_dir)
    if dupes:
        print(f"  Found {len(dupes)} near-duplicate pairs:")
        for p1, p2, score in dupes:
            print(f"    [{score:.2f}] {p1.name} ↔ {p2.name}")
    else:
        print("  No near-duplicates found.")

    # 2. Orphan wikilinks
    print("\nChecking for orphan wikilinks...")
    orphans = find_orphan_wikilinks(wiki_dir)
    if orphans:
        print(f"  Found {len(orphans)} orphan links:")
        for o in orphans[:20]:
            print(f"    {o}")
        if len(orphans) > 20:
            print(f"    ... and {len(orphans) - 20} more")
    else:
        print("  No orphan wikilinks.")

    # 3. Promotable observations
    print("\nScanning observations for promotion candidates...")
    count = promote_observations(wiki_dir)
    print(f"  {count} promotable observations found (review manually).")

    print(f"\nLint complete.")


if __name__ == "__main__":
    run_lint(WIKI_DIR)
