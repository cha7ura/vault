#!/usr/bin/env python3
"""
Stage 1 — Extract speaker embeddings from NeMo diarization output.

Reads TitaNet speaker embeddings (192-dim) computed by NeMo's diarization
pipeline and stores per-speaker centroid embeddings in the speaker_embeddings
table.

Usage:
    # Single episode
    python scripts/agents/extract_embeddings.py \
        --nemo-dir /path/to/nemo_outputs --episode-id abc123

    # Batch mode — scan all subdirs, match against episodes by youtube_id
    python scripts/agents/extract_embeddings.py \
        --nemo-dir /path/to/nemo_outputs
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np

# Allow running as `python scripts/agents/extract_embeddings.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.agents.config import BATCH_INSERT_SIZE
from scripts.agents.db import fetch_all, fetch_one, execute, vec_str


# ---------------------------------------------------------------------------
# Locate NeMo embedding files
# ---------------------------------------------------------------------------

def find_embedding_files(session_dir: Path) -> dict[str, object] | None:
    """
    Search *session_dir* for NeMo speaker embeddings.

    Returns a dict ``{"type": ..., "path": ...}`` describing what was found,
    or ``None`` if nothing recognisable exists.

    Supported layouts
    -----------------
    1. speaker_embeddings.pkl  — dict {speaker_id: ndarray(192,)}
    2. scale*/embeddings.npy + labels.npy
    3. speaker_outputs/embeddings.npy + labels.npy
    """
    speaker_out = session_dir / "speaker_outputs"

    # Pattern 1: pickle dict
    pkl_path = speaker_out / "speaker_embeddings.pkl"
    if not pkl_path.exists():
        pkl_path = session_dir / "speaker_embeddings.pkl"
    if pkl_path.exists():
        return {"type": "pkl", "path": pkl_path}

    # Pattern 2: scale-specific subdirectories
    if speaker_out.exists():
        for scale_dir in sorted(speaker_out.glob("scale*")):
            emb = scale_dir / "embeddings.npy"
            lbl = scale_dir / "labels.npy"
            if emb.exists() and lbl.exists():
                return {"type": "npy_pair", "embeddings": emb, "labels": lbl}

    # Pattern 3: embeddings.npy + labels.npy at speaker_outputs level
    emb = speaker_out / "embeddings.npy"
    lbl = speaker_out / "labels.npy"
    if emb.exists() and lbl.exists():
        return {"type": "npy_pair", "embeddings": emb, "labels": lbl}

    return None


# ---------------------------------------------------------------------------
# Compute per-speaker centroids
# ---------------------------------------------------------------------------

def load_speaker_centroids(info: dict) -> dict[str, list[float]]:
    """
    Return ``{speaker_label: centroid_list}`` from the embedding artefacts
    described by *info* (as returned by :func:`find_embedding_files`).
    """
    if info["type"] == "pkl":
        with open(info["path"], "rb") as fh:
            data = pickle.load(fh)
        # data is expected to be {speaker_id: ndarray} or similar mapping
        centroids: dict[str, list[float]] = {}
        for spk, vec in data.items():
            arr = np.asarray(vec, dtype=np.float64)
            if arr.ndim == 2:
                arr = arr.mean(axis=0)
            centroids[str(spk)] = arr.tolist()
        return centroids

    if info["type"] == "npy_pair":
        embeddings = np.load(info["embeddings"])  # (N, 192)
        labels = np.load(info["labels"])           # (N,)
        unique_labels = np.unique(labels)
        centroids = {}
        for lbl in unique_labels:
            mask = labels == lbl
            centroid = embeddings[mask].mean(axis=0).astype(np.float64)
            centroids[str(lbl)] = centroid.tolist()
        return centroids

    raise ValueError(f"Unknown embedding type: {info['type']}")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def existing_labels(episode_id: str) -> set[str]:
    """Return the set of speaker_labels already stored for *episode_id*."""
    rows = fetch_all(
        "SELECT speaker_label FROM speaker_embeddings WHERE episode_id=%s",
        (episode_id,),
    )
    return {r["speaker_label"] for r in rows}


def store_embeddings(episode_id: str, centroids: dict[str, list[float]]) -> int:
    """Insert centroid rows, skipping labels that already exist. Return count."""
    already = existing_labels(episode_id)
    to_insert = [
        (episode_id, label, vec_str(vec))
        for label, vec in centroids.items()
        if label not in already
    ]

    if not to_insert:
        return 0

    inserted = 0
    for row in to_insert:
        execute(
            """
            INSERT INTO speaker_embeddings (episode_id, speaker_label, embedding)
            VALUES (%s, %s, %s::vector)
            """,
            row,
        )
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Episode resolution
# ---------------------------------------------------------------------------

def resolve_episode_id(youtube_id: str) -> str | None:
    """Look up the episode UUID for a given youtube_id."""
    row = fetch_one(
        "SELECT id FROM episodes WHERE youtube_id=%s LIMIT 1",
        (youtube_id,),
    )
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_episode(nemo_dir: Path, episode_id: str, subdir: str | None = None) -> bool:
    """
    Extract and store embeddings for a single episode.
    Returns True on success, False on skip/error.
    """
    session_dir = nemo_dir / subdir if subdir else nemo_dir
    info = find_embedding_files(session_dir)
    if info is None:
        print(f"  [skip] no embedding files found in {session_dir}")
        return False

    try:
        centroids = load_speaker_centroids(info)
    except Exception as exc:
        print(f"  [error] failed to load embeddings: {exc}")
        return False

    if not centroids:
        print(f"  [skip] no speakers found in embeddings")
        return False

    count = store_embeddings(episode_id, centroids)
    if count == 0:
        print(f"  [skip] all {len(centroids)} speakers already stored")
    else:
        print(f"  [ok] inserted {count} speaker embeddings ({len(centroids)} total speakers)")
    return True


def run_single(nemo_dir: Path, episode_id: str):
    """Process a single episode given its ID."""
    print(f"Processing episode {episode_id} ...")
    process_episode(nemo_dir, episode_id)


def run_batch(nemo_dir: Path):
    """
    Scan subdirectories of *nemo_dir*, treating each folder name as a
    youtube_id, and process all matching episodes.
    """
    subdirs = sorted(
        p.name for p in nemo_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    print(f"Found {len(subdirs)} subdirectories in {nemo_dir}")

    processed = 0
    skipped = 0
    errors = 0

    for yt_id in subdirs:
        episode_id = resolve_episode_id(yt_id)
        if episode_id is None:
            print(f"  [{yt_id}] no matching episode in DB — skipping")
            skipped += 1
            continue

        print(f"  [{yt_id}] episode {episode_id}")
        ok = process_episode(nemo_dir, episode_id, subdir=yt_id)
        if ok:
            processed += 1
        else:
            errors += 1

    print(f"\nDone — {processed} processed, {skipped} skipped, {errors} errors")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 1: extract speaker embeddings from NeMo diarization output",
    )
    parser.add_argument(
        "--nemo-dir", type=Path, required=True,
        help="Root directory containing NeMo diarization outputs",
    )
    parser.add_argument(
        "--episode-id", type=str, default=None,
        help="Process a single episode by its UUID (default: batch mode)",
    )
    args = parser.parse_args()

    if not args.nemo_dir.exists():
        print(f"Error: {args.nemo_dir} does not exist")
        sys.exit(1)

    if args.episode_id:
        run_single(args.nemo_dir, args.episode_id)
    else:
        run_batch(args.nemo_dir)


if __name__ == "__main__":
    main()
