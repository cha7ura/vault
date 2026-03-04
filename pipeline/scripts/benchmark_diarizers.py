"""Benchmark whisper-diarization on a single episode.

Usage:
    cd pipeline && uv run python scripts/benchmark_diarizers.py data/audio/doac/jDG1m_b5Ih0_16k.wav
"""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_whisper_diarization(audio_path: str) -> dict | None:
    """Run whisper-diarization subprocess and return results + timing."""
    try:
        from pipeline.core.diarizer_whisper import run_whisper_diarization as run_wd
    except ImportError:
        print("\n[SKIP] whisper-diarization not installed")
        return None

    print(f"\n{'='*60}")
    print("WHISPER-DIARIZATION PIPELINE")
    print(f"{'='*60}", flush=True)

    start = time.time()
    try:
        transcript = run_wd(audio_path, whisper_model="medium.en")
        elapsed = time.time() - start
    except Exception as e:
        print(f"Error: {e}")
        return None

    print(f"\nCompleted in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Speakers found: {transcript.speakers}")
    print(f"Total segments: {len(transcript.segments)}")
    print(f"\nFirst 20 segments:")
    print("-" * 60)
    for seg in transcript.segments[:20]:
        print(f"[{seg.start:7.1f}s - {seg.end:7.1f}s] {seg.speaker}: {seg.text[:80]}")

    output = {
        "diarizer": "whisper-diarization",
        "duration_s": elapsed,
        "speakers": transcript.speakers,
        "n_segments": len(transcript.segments),
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "speaker": s.speaker,
            }
            for s in transcript.segments
        ],
    }
    return output


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_diarizers.py <audio_path>")
        sys.exit(1)

    audio_path = sys.argv[1]
    print(f"Audio: {audio_path}")

    result = run_whisper_diarization(audio_path)
    if not result:
        print("Diarization failed")
        sys.exit(1)

    out_dir = Path("data/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    video_id = Path(audio_path).stem.replace("_16k", "")
    out_file = out_dir / f"{video_id}_benchmark.json"
    with open(out_file, "w") as f:
        json.dump([result], f, indent=2)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
