"""Benchmark diarizers on a single episode.

Usage:
    cd pipeline && uv run python scripts/benchmark_diarizers.py data/audio/doac/jDG1m_b5Ih0_16k.wav

Runs PyAnnote diarizer (and optionally whisper-diarization) on the given
audio file, printing timing and first N segments from each.

Caches transcription output to avoid re-running the slow STT step.
"""

import sys
import time
import json
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

CACHE_DIR = Path("data/cache")


def _cache_path(audio_path: str, label: str) -> Path:
    video_id = Path(audio_path).stem.replace("_16k", "")
    return CACHE_DIR / f"{video_id}_{label}.json"


def _save_cache(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _load_cache(path: Path) -> list[dict] | None:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def run_pyannote(audio_path: str, device: str = "mps") -> dict:
    """Run PyAnnote diarization pipeline and return results + timing."""
    from pipeline.core.diarizer_pyannote import (
        TranscriptSegment,
        transcribe_with_faster_whisper,
        diarize_with_pyannote,
        merge_diarization_with_transcript,
    )

    # Get HF token from huggingface_hub cache
    from huggingface_hub import HfApi
    api = HfApi()
    token = api.token

    print(f"\n{'='*60}")
    print(f"PYANNOTE PIPELINE (device={device})")
    print(f"{'='*60}", flush=True)

    # Step 1: Transcription — check cache first
    whisper_device = "cpu" if device == "mps" else device
    cache = _cache_path(audio_path, "transcription")
    cached = _load_cache(cache)

    if cached:
        print(f"\n[1/3] Loading cached transcription ({len(cached)} segments)...", flush=True)
        transcript_segments = [
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"])
            for s in cached
        ]
        t1_elapsed = 0.0
    else:
        print(f"\n[1/3] Transcribing with faster-whisper (medium.en, device={whisper_device})...", flush=True)
        t1 = time.time()
        transcript_segments = transcribe_with_faster_whisper(
            audio_path, model_size="medium.en", device=whisper_device,
        )
        t1_elapsed = time.time() - t1
        print(f"      Done in {t1_elapsed:.1f}s — {len(transcript_segments)} segments", flush=True)
        # Cache transcription
        _save_cache(cache, [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in transcript_segments
        ])
        print(f"      Cached to {cache}")

    # Step 2: Diarization (PyAnnote, supports MPS)
    print(f"\n[2/3] Running PyAnnote speaker diarization (device={device})...", flush=True)
    t2 = time.time()
    diarization_segments = diarize_with_pyannote(
        audio_path, hf_token=token, device=device,
    )
    t2_elapsed = time.time() - t2
    print(f"      Done in {t2_elapsed:.1f}s — {len(diarization_segments)} speaker turns", flush=True)

    # Step 3: Merge
    print("\n[3/3] Merging transcription with speaker labels...", flush=True)
    t3 = time.time()
    transcript = merge_diarization_with_transcript(transcript_segments, diarization_segments)
    t3_elapsed = time.time() - t3
    print(f"      Done in {t3_elapsed:.1f}s", flush=True)

    elapsed = t1_elapsed + t2_elapsed + t3_elapsed

    print(f"\nCompleted in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Speakers found: {transcript.speakers}")
    print(f"Total segments: {len(transcript.segments)}")
    print(f"\nFirst 20 segments:")
    print("-" * 60)
    for seg in transcript.segments[:20]:
        print(f"[{seg.start:7.1f}s - {seg.end:7.1f}s] {seg.speaker}: {seg.text[:80]}")

    output = {
        "diarizer": "pyannote",
        "device": device,
        "transcription_time_s": t1_elapsed,
        "diarization_time_s": t2_elapsed,
        "merge_time_s": t3_elapsed,
        "total_time_s": elapsed,
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
        print("Usage: python benchmark_diarizers.py <audio_path> [--device mps|cpu]")
        sys.exit(1)

    audio_path = sys.argv[1]
    device = "mps"
    if "--device" in sys.argv:
        device = sys.argv[sys.argv.index("--device") + 1]

    print(f"Audio: {audio_path}")
    print(f"Device: {device}")

    results = []

    # Run PyAnnote
    pyannote_result = run_pyannote(audio_path, device=device)
    results.append(pyannote_result)

    # Run whisper-diarization (if available)
    wd_result = run_whisper_diarization(audio_path)
    if wd_result:
        results.append(wd_result)

    # Save results
    out_dir = Path("data/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    video_id = Path(audio_path).stem.replace("_16k", "")
    out_file = out_dir / f"{video_id}_benchmark.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_file}")

    # Summary
    if len(results) > 1:
        print(f"\n{'='*60}")
        print("COMPARISON SUMMARY")
        print(f"{'='*60}")
        for r in results:
            print(f"\n{r['diarizer']}:")
            print(f"  Time: {r.get('total_time_s', r.get('duration_s', 0)):.1f}s")
            print(f"  Speakers: {r['speakers']}")
            print(f"  Segments: {r['n_segments']}")


if __name__ == "__main__":
    main()
