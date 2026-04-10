#!/usr/bin/env python3
"""
Stage 4: Export agent memories to JSON files for inspection and debugging.

Usage:
    python -m scripts.agents.export_memory --channel diary-of-a-ceo
    python -m scripts.agents.export_memory --person-slug steven-bartlett
"""

import argparse
import json
import sys
from pathlib import Path

from scripts.agents.config import ROOT_DIR
from scripts.agents.db import fetch_all, fetch_one


def export_person(person_id: str, person_name: str, person_slug: str, output_dir: Path):
    """Export a single person's agent memory to JSON."""
    row = fetch_one(
        """
        SELECT memory, memory_version, turns_processed, updated_at
        FROM agent_memories
        WHERE person_id=%s
        """,
        (person_id,),
    )

    if not row:
        print(f"  {person_name}: no memory found, skipping")
        return

    export = {
        "person_id": person_id,
        "name": person_name,
        "slug": person_slug,
        "memory_version": row["memory_version"],
        "turns_processed": row["turns_processed"],
        "updated_at": row["updated_at"],
        "memory": row["memory"],
    }

    output_file = output_dir / f"{person_slug}.json"
    with open(output_file, "w") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print(f"  {person_name}: exported (v{row['memory_version']}, {row['turns_processed']} turns)")


def main():
    parser = argparse.ArgumentParser(description="Export agent memories to JSON")
    parser.add_argument("--channel", help="Channel slug (export all people)")
    parser.add_argument("--person-slug", help="Export single person")
    parser.add_argument("--output-dir", help="Output directory", default="data/agents")
    args = parser.parse_args()

    if not args.channel and not args.person_slug:
        print("Provide --channel or --person-slug")
        sys.exit(1)

    output_dir = ROOT_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.person_slug:
        people = fetch_all(
            "SELECT id, name, slug FROM people WHERE slug=%s",
            (args.person_slug,),
        )
        if not people:
            print(f"Person '{args.person_slug}' not found")
            sys.exit(1)
    else:
        people = fetch_all(
            """
            SELECT p.id, p.name, p.slug
            FROM agent_memories am
            JOIN people p ON p.id = am.person_id
            """
        )

    print(f"Exporting {len(people)} agent memories to {output_dir}/\n")

    for person in people:
        export_person(person["id"], person["name"], person["slug"], output_dir)

    print(f"\nDone.")


if __name__ == "__main__":
    main()
