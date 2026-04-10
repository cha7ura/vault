"""PyAnnote-based diarization pipeline.

Combines faster-whisper STT with PyAnnote speaker diarization.
ML dependencies (pyannote.audio, faster-whisper) are lazy-imported so the
pure merge logic can be tested without installing heavy GPU libraries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DiarizationSegment:
    """A single speaker turn from the diarization model."""
    start: float
    end: float
    speaker: str


@dataclass
class TranscriptSegment:
    """A single text segment from the STT model."""
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class DiarizedTranscript:
    """Final output: transcript segments with speaker labels."""
    segments: list[TranscriptSegment] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    full_text: str = ""


# ---------------------------------------------------------------------------
# Pure logic — fully testable without ML deps
# ---------------------------------------------------------------------------

def _friendly_speaker_name(raw: str) -> str:
    """Convert 'SPEAKER_00' -> 'Speaker 0', 'SPEAKER_01' -> 'Speaker 1', etc."""
    m = re.search(r"(\d+)$", raw)
    if m:
        return f"Speaker {int(m.group(1))}"
    return raw


def merge_diarization_with_transcript(
    transcript_segments: list[TranscriptSegment],
    diarization_segments: list[DiarizationSegment],
) -> DiarizedTranscript:
    """Assign speaker labels to transcript segments using midpoint overlap.

    For each transcript segment the midpoint ``(start + end) / 2`` is
    computed. The diarization segment that *contains* that midpoint
    determines the speaker label.  If no diarization data is available the
    speaker stays ``None``.
    """
    labelled: list[TranscriptSegment] = []
    seen_speakers: dict[str, str] = {}  # raw -> friendly

    for seg in transcript_segments:
        midpoint = (seg.start + seg.end) / 2.0
        speaker: str | None = None

        for dseg in diarization_segments:
            if dseg.start <= midpoint < dseg.end:
                friendly = _friendly_speaker_name(dseg.speaker)
                seen_speakers[dseg.speaker] = friendly
                speaker = friendly
                break

        labelled.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speaker,
            )
        )

    speakers = list(dict.fromkeys(seen_speakers.values()))  # unique, ordered
    full_text = " ".join(seg.text for seg in labelled)

    return DiarizedTranscript(
        segments=labelled,
        speakers=speakers,
        full_text=full_text,
    )


# ---------------------------------------------------------------------------
# ML wrappers — lazy imports, NOT tested in unit tests
# ---------------------------------------------------------------------------

def transcribe_with_faster_whisper(
    audio_path: Path | str,
    model_size: str = "large-v3",
    device: str = "cpu",
) -> list[TranscriptSegment]:
    """Run faster-whisper on *audio_path* and return transcript segments."""
    from faster_whisper import WhisperModel  # lazy import

    model = WhisperModel(model_size, device=device, compute_type="int8")
    segments_iter, _info = model.transcribe(str(audio_path), beam_size=5)

    return [
        TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
        for s in segments_iter
    ]


def diarize_with_pyannote(
    audio_path: Path | str,
    hf_token: str,
    device: str = "cpu",
) -> list[DiarizationSegment]:
    """Run PyAnnote speaker diarization on *audio_path*."""
    from pyannote.audio import Pipeline as PyannotePipeline  # lazy import

    pipeline = PyannotePipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    pipeline.to(device)

    diarization = pipeline(str(audio_path))

    results: list[DiarizationSegment] = []
    for turn, _track, speaker in diarization.itertracks(yield_label=True):
        results.append(
            DiarizationSegment(start=turn.start, end=turn.end, speaker=speaker)
        )
    return results


def run_pyannote_pipeline(
    audio_path: Path | str,
    hf_token: str,
    whisper_model: str = "large-v3",
    device: str = "cpu",
) -> DiarizedTranscript:
    """Full pipeline: faster-whisper STT + PyAnnote diarization + merge.

    Note: faster-whisper (CTranslate2) only supports cpu/cuda, not mps.
    PyAnnote supports mps. When device='mps', transcription runs on cpu
    while diarization uses mps for GPU acceleration.
    """
    # CTranslate2 doesn't support MPS — always use cpu for transcription
    whisper_device = "cpu" if device == "mps" else device
    transcript_segments = transcribe_with_faster_whisper(
        audio_path, model_size=whisper_model, device=whisper_device,
    )
    diarization_segments = diarize_with_pyannote(
        audio_path, hf_token=hf_token, device=device,
    )
    return merge_diarization_with_transcript(transcript_segments, diarization_segments)
