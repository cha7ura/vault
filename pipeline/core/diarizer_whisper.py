"""Whisper-diarization wrapper.

Wraps MahmoudAshraf97/whisper-diarization as a subprocess.  Only the output
parser (``parse_whisper_diarization_output``) is unit-tested; the subprocess
runner (``run_whisper_diarization``) requires the external tool installed.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes (independent from PyAnnote module)
# ---------------------------------------------------------------------------

@dataclass
class TranscriptSegment:
    """A single timestamped text segment with optional speaker label."""
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class DiarizedTranscript:
    """Collection of speaker-labelled transcript segments."""
    segments: list[TranscriptSegment] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    full_text: str = ""


# ---------------------------------------------------------------------------
# Pure logic — fully testable
# ---------------------------------------------------------------------------

def parse_whisper_diarization_output(raw_output: str) -> DiarizedTranscript:
    """Parse text output from whisper-diarization.

    Expected line format::

        [0.00s - 5.20s] Speaker 0: Hello and welcome.

    Returns a ``DiarizedTranscript`` with segments, unique sorted speakers,
    and concatenated full text.
    """
    if not raw_output.strip():
        return DiarizedTranscript(segments=[], speakers=[], full_text="")

    pattern = re.compile(
        r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s*\d+):\s*(.*)"
    )

    segments: list[TranscriptSegment] = []
    speakers_set: set[str] = set()

    for line in raw_output.strip().splitlines():
        match = pattern.match(line.strip())
        if match:
            start = float(match.group(1))
            end = float(match.group(2))
            speaker = match.group(3).strip()
            text = match.group(4).strip()
            segments.append(
                TranscriptSegment(start=start, end=end, text=text, speaker=speaker)
            )
            speakers_set.add(speaker)

    speakers = sorted(speakers_set)

    return DiarizedTranscript(
        segments=segments,
        speakers=speakers,
        full_text=" ".join(s.text for s in segments),
    )


# ---------------------------------------------------------------------------
# Subprocess runner — NOT tested in unit tests
# ---------------------------------------------------------------------------

def run_whisper_diarization(
    audio_path: Path,
    whisper_model: str = "medium.en",
    device: str = "cpu",
    no_stem: bool = False,
    batch_size: int = 8,
) -> DiarizedTranscript:
    """Run whisper-diarization as a subprocess.

    Invokes ``python3 -m diarize`` with the given arguments and parses the
    resulting output file (or stdout) into a ``DiarizedTranscript``.
    """
    cmd = [
        "python3", "-m", "diarize",
        "-a", str(audio_path),
        "--whisper-model", whisper_model,
        "--device", device,
        "--batch-size", str(batch_size),
    ]
    if no_stem:
        cmd.append("--no-stem")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"whisper-diarization failed: {result.stderr}")

    # whisper-diarization writes output to a .txt file next to the audio
    output_path = audio_path.with_suffix(".txt")
    if output_path.exists():
        return parse_whisper_diarization_output(output_path.read_text())

    return parse_whisper_diarization_output(result.stdout)
