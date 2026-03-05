"""Add words (JSON) and youtube_text (TEXT) columns to the segments table.

Usage:
    python -m pipeline.scripts.migrate_add_word_columns
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "vault.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}, skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check which columns already exist
    cursor.execute("PRAGMA table_info(segments)")
    existing = {row[1] for row in cursor.fetchall()}

    if "words" not in existing:
        cursor.execute("ALTER TABLE segments ADD COLUMN words JSON")
        print("Added 'words' column.")
    else:
        print("'words' column already exists.")

    if "youtube_text" not in existing:
        cursor.execute("ALTER TABLE segments ADD COLUMN youtube_text TEXT")
        print("Added 'youtube_text' column.")
    else:
        print("'youtube_text' column already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
