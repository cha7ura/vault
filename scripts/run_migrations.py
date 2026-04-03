#!/usr/bin/env python3
"""Run Supabase migrations via psycopg2.

Usage:
    # Apply all unapplied migrations
    python scripts/run_migrations.py

    # Apply a specific migration
    python scripts/run_migrations.py --file supabase/migrations/008_pipeline_columns.sql

    # Dry run — show what would be applied
    python scripts/run_migrations.py --dry-run
"""
import argparse
import os
import re
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env.local")

MIGRATIONS_DIR = ROOT_DIR / "supabase" / "migrations"
DATABASE_URL = os.environ["DATABASE_URL"]


def get_migration_files() -> list[Path]:
    """Get all .sql migration files sorted by name."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def get_applied_migrations(cur) -> set[str]:
    """Check which migrations have been tracked. Creates tracking table if needed."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("SELECT name FROM _migrations")
    return {row[0] for row in cur.fetchall()}


def apply_migration(cur, path: Path, dry_run: bool = False) -> bool:
    """Apply a single migration file. Returns True if applied."""
    name = path.name
    sql = path.read_text()

    if dry_run:
        print(f"  [DRY RUN] Would apply: {name}")
        return False

    try:
        cur.execute(sql)
        cur.execute("INSERT INTO _migrations (name) VALUES (%s) ON CONFLICT DO NOTHING", (name,))
        print(f"  Applied: {name}")
        return True
    except Exception as e:
        print(f"  FAILED: {name} — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run Supabase migrations")
    parser.add_argument("--file", help="Apply a specific migration file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {args.file}")
            return
        print(f"Applying single migration: {path.name}")
        apply_migration(cur, path, dry_run=args.dry_run)
    else:
        applied = get_applied_migrations(cur)
        files = get_migration_files()
        pending = [f for f in files if f.name not in applied]

        if not pending:
            print("All migrations already applied.")
        else:
            print(f"{len(pending)} migration(s) to apply:\n")
            for path in pending:
                apply_migration(cur, path, dry_run=args.dry_run)

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
