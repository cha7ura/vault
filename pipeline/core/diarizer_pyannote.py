"""Pyannote 3.1 diarization wrapper.

Same interface as diarizer_whisper.py — runs diarize.py with --diarizer pyannote
and parses the JSON output into a DiarizedTranscript.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.core.diarizer_whisper import (
    DiarizedTranscript,
    parse_whisper_diarization_json,
    parse_whisper_diarization_output,
)


# Path to the vendored diarize.py script
DIARIZE_SCRIPT = Path(__file__).parent.parent.parent / "vendor" / "whisper-diarization" / "diarize.py"


def run_pyannote_diarization(
    audio_path: Path,
    whisper_model: str = "large-v3",
    device: str = "cuda",
    batch_size: int = 16,
    hf_token: str | None = None,
    whisper_cache_path: Path | None = None,
) -> DiarizedTranscript:
    """Run Whisper transcription + Pyannote 3.1 diarization.

    If whisper_cache_path is provided, skips Whisper and reuses cached output.
    """
    cmd = [
        "python3", str(DIARIZE_SCRIPT),
        "-a", str(audio_path),
        "--whisper-model", whisper_model,
        "--device", device,
        "--batch-size", str(batch_size),
        "--language", "en",
        "--diarizer", "pyannote",
    ]

    if hf_token:
        cmd.extend(["--hf-token", hf_token])

    if whisper_cache_path:
        cmd.extend(["--whisper-cache", str(whisper_cache_path)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"pyannote diarization failed: {result.stderr}")

    json_output = Path(audio_path).with_suffix(".json")
    if json_output.exists():
        return parse_whisper_diarization_json(json_output)

    txt_output = Path(audio_path).with_suffix(".txt")
    if txt_output.exists():
        return parse_whisper_diarization_output(txt_output.read_text())

    return parse_whisper_diarization_output(result.stdout)
