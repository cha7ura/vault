"""Compare NeMo MSDD vs Pyannote 3.1 on the same audio.

Runs Whisper once (cached), then both diarizers sequentially,
and prints a side-by-side comparison.

Usage:
    cd pipeline && uv run python scripts/benchmark_comparison.py data/audio/test.wav
    cd pipeline && uv run python scripts/benchmark_comparison.py data/audio/test.wav --hf-token hf_xxx
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "vendor" / "whisper-diarization"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_comparison(audio_path: str, whisper_model: str, device: str,
                   batch_size: int, hf_token: str | None):
    from diarize import (
        run_whisper_transcription,
        run_diarization,
        run_postprocessing,
        save_whisper_cache,
    )

    cache_dir = str(Path(audio_path).parent / f".whisper_cache_{Path(audio_path).stem}")
    base = Path(audio_path).with_suffix("")

    # ---- Phase A: Whisper (shared, run once) ----
    print(f"\n{'='*70}")
    print("PHASE A: WHISPER TRANSCRIPTION (shared)")
    print(f"{'='*70}\n")

    t0 = time.time()
    whisper_result = run_whisper_transcription(
        audio_path, whisper_model, device, batch_size, language="en",
    )
    whisper_time = time.time() - t0

    cache_path = save_whisper_cache(whisper_result, cache_dir)

    print(f"\nWhisper completed in {whisper_time:.1f}s")
    print(f"  Words: {len(whisper_result['word_timestamps'])}")
    print(f"  Duration: {whisper_result['audio_duration']:.0f}s")
    print(f"  Cache saved: {cache_dir}")

    results = {}

    # ---- Phase B1: NeMo MSDD ----
    print(f"\n{'='*70}")
    print("PHASE B1: NeMo MSDD DIARIZATION")
    print(f"{'='*70}\n")

    t0 = time.time()
    msdd_speaker_ts = run_diarization(
        whisper_result["audio_waveform"], "msdd", device,
    )
    msdd_diarize_time = time.time() - t0

    t0 = time.time()
    msdd_segments = run_postprocessing(
        whisper_result["word_timestamps"], msdd_speaker_ts,
        whisper_result["language"], audio_path,
    )
    msdd_post_time = time.time() - t0

    msdd_speakers = {s["speaker"] for s in msdd_segments}

    # Save MSDD output separately
    msdd_json_path = f"{base}_msdd.json"
    with open(msdd_json_path, "w", encoding="utf-8") as f:
        json.dump(msdd_segments, f, ensure_ascii=False, indent=2)

    results["nemo-msdd"] = {
        "diarizer": "nemo-msdd",
        "diarize_time_s": round(msdd_diarize_time, 1),
        "postprocess_time_s": round(msdd_post_time, 1),
        "total_time_s": round(msdd_diarize_time + msdd_post_time, 1),
        "n_speakers": len(msdd_speakers),
        "n_segments": len(msdd_segments),
        "n_speaker_turns": len(msdd_speaker_ts),
        "output_json": msdd_json_path,
    }

    # ---- Phase B2: Pyannote 3.1 ----
    print(f"\n{'='*70}")
    print("PHASE B2: PYANNOTE 3.1 DIARIZATION")
    print(f"{'='*70}\n")

    t0 = time.time()
    pyannote_speaker_ts = run_diarization(
        whisper_result["audio_waveform"], "pyannote", device, hf_token=hf_token,
    )
    pyannote_diarize_time = time.time() - t0

    t0 = time.time()
    pyannote_segments = run_postprocessing(
        whisper_result["word_timestamps"], pyannote_speaker_ts,
        whisper_result["language"], audio_path,
    )
    pyannote_post_time = time.time() - t0

    pyannote_speakers = {s["speaker"] for s in pyannote_segments}

    # Save Pyannote output separately
    pyannote_json_path = f"{base}_pyannote.json"
    with open(pyannote_json_path, "w", encoding="utf-8") as f:
        json.dump(pyannote_segments, f, ensure_ascii=False, indent=2)

    results["pyannote-3.1"] = {
        "diarizer": "pyannote-3.1",
        "diarize_time_s": round(pyannote_diarize_time, 1),
        "postprocess_time_s": round(pyannote_post_time, 1),
        "total_time_s": round(pyannote_diarize_time + pyannote_post_time, 1),
        "n_speakers": len(pyannote_speakers),
        "n_segments": len(pyannote_segments),
        "n_speaker_turns": len(pyannote_speaker_ts),
        "output_json": pyannote_json_path,
    }

    # ---- Summary ----
    print(f"\n{'='*70}")
    print("COMPARISON SUMMARY")
    print(f"{'='*70}\n")

    print(f"Audio: {audio_path}")
    print(f"Duration: {whisper_result['audio_duration']:.0f}s")
    print(f"Whisper model: {whisper_model}")
    print(f"Whisper time: {whisper_time:.1f}s (shared, not counted in diarizer time)")
    print()

    header = f"{'Metric':<30} {'NeMo MSDD':>15} {'Pyannote 3.1':>15}"
    print(header)
    print("-" * len(header))
    print(f"{'Diarization time':<30} {results['nemo-msdd']['diarize_time_s']:>14.1f}s {results['pyannote-3.1']['diarize_time_s']:>14.1f}s")
    print(f"{'Post-processing time':<30} {results['nemo-msdd']['postprocess_time_s']:>14.1f}s {results['pyannote-3.1']['postprocess_time_s']:>14.1f}s")
    print(f"{'Total (diarize + post)':<30} {results['nemo-msdd']['total_time_s']:>14.1f}s {results['pyannote-3.1']['total_time_s']:>14.1f}s")
    print(f"{'Speakers detected':<30} {results['nemo-msdd']['n_speakers']:>15} {results['pyannote-3.1']['n_speakers']:>15}")
    print(f"{'Speaker turns':<30} {results['nemo-msdd']['n_speaker_turns']:>15} {results['pyannote-3.1']['n_speaker_turns']:>15}")
    print(f"{'Output segments':<30} {results['nemo-msdd']['n_segments']:>15} {results['pyannote-3.1']['n_segments']:>15}")
    print()
    print(f"MSDD output:     {msdd_json_path}")
    print(f"Pyannote output: {pyannote_json_path}")

    # Save benchmark results
    benchmark_path = f"{base}_benchmark.json"
    benchmark = {
        "audio": audio_path,
        "audio_duration_s": whisper_result["audio_duration"],
        "whisper_model": whisper_model,
        "whisper_time_s": round(whisper_time, 1),
        "results": results,
    }
    with open(benchmark_path, "w", encoding="utf-8") as f:
        json.dump(benchmark, f, ensure_ascii=False, indent=2)

    print(f"Benchmark:       {benchmark_path}")

    # Show first 5 segments from each for quick visual comparison
    print(f"\n{'='*70}")
    print("SAMPLE SEGMENTS (first 5)")
    print(f"{'='*70}")

    for name, segs in [("NeMo MSDD", msdd_segments), ("Pyannote 3.1", pyannote_segments)]:
        print(f"\n--- {name} ---")
        for seg in segs[:5]:
            print(f"  [{seg['start']:7.1f}s - {seg['end']:7.1f}s] {seg['speaker']}: {seg['text'][:80]}")


def main():
    parser = argparse.ArgumentParser(description="Compare NeMo MSDD vs Pyannote 3.1 diarization")
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--whisper-model", default="large-v3", help="Whisper model (default: large-v3)")
    parser.add_argument("--device", default="cuda", help="Device (default: cuda)")
    parser.add_argument("--batch-size", type=int, default=16, help="Whisper batch size (default: 16)")
    parser.add_argument("--hf-token", default=None, help="HuggingFace token for Pyannote")

    args = parser.parse_args()
    run_comparison(args.audio, args.whisper_model, args.device, args.batch_size, args.hf_token)


if __name__ == "__main__":
    main()
