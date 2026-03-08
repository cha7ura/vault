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

from scripts.agents.config import get_supabase, ROOT_DIR


def export_person(sb, person_id: str, person_name: str, person_slug: str, output_dir: Path):
    """Export a single person's agent memory to JSON."""
    mem = (
        sb.table("agent_memories")
        .select("memory, memory_version, turns_processed, updated_at")
        .eq("person_id", person_id)
        .execute()
    )

    if not mem.data:
        print(f"  {person_name}: no memory found, skipping")
        return

    row = mem.data[0]
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

    sb = get_supabase()
    output_dir = ROOT_DIR / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.person_slug:
        person = sb.table("people").select("id, name, slug").eq("slug", args.person_slug).execute()
        if not person.data:
            print(f"Person '{args.person_slug}' not found")
            sys.exit(1)
        people = person.data
    else:
        all_memories = (
            sb.table("agent_memories")
            .select("person_id, people(id, name, slug)")
            .execute()
        )
        people = [row["people"] for row in all_memories.data if row.get("people")]

    print(f"Exporting {len(people)} agent memories to {output_dir}/\n")

    for person in people:
        export_person(sb, person["id"], person["name"], person["slug"], output_dir)

    print(f"\nDone.")


if __name__ == "__main__":
    main()
