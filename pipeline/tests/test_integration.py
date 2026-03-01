import pytest
from pathlib import Path

from pipeline.core.downloader import extract_video_id, download_audio, get_video_metadata
from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end


@pytest.mark.integration
def test_download_and_preprocess(tmp_path):
    """End-to-end: download a short YouTube video and preprocess it.
    Uses a Creative Commons test video. Skip with: pytest -m "not integration"
    """
    video_id = "jNQXAC9IVRw"  # "Me at the zoo" — first YouTube video, 19 seconds

    audio_dir = tmp_path / "audio"
    audio_path = download_audio(video_id, audio_dir)
    assert audio_path.exists() or (audio_dir / f"{video_id}.wav").exists()

    wav_files = list(audio_dir.glob("*.wav"))
    assert len(wav_files) >= 1
    audio_path = wav_files[0]

    mono_path = tmp_path / "mono.wav"
    convert_to_mono_16k(audio_path, mono_path)
    assert mono_path.exists()

    intro_end = detect_intro_end(mono_path)
    assert intro_end >= 0.0


@pytest.mark.integration
def test_get_video_metadata():
    meta = get_video_metadata("jNQXAC9IVRw")
    assert meta["youtube_id"] == "jNQXAC9IVRw"
    assert "zoo" in meta["title"].lower()
    assert meta["duration"] > 0
