import numpy as np
import pytest
import soundfile as sf
from pathlib import Path

from pipeline.core.preprocessor import convert_to_mono_16k, detect_intro_end


@pytest.fixture
def sample_audio(tmp_path) -> Path:
    """Create synthetic audio: loud intro (3s) + silence (1s) + speech (6s)."""
    sr = 44100
    intro = np.random.randn(3 * sr).astype(np.float32) * 0.8
    silence = np.zeros(1 * sr, dtype=np.float32)
    speech = np.random.randn(6 * sr).astype(np.float32) * 0.2
    audio = np.concatenate([intro, silence, speech])
    path = tmp_path / "test_audio.wav"
    sf.write(str(path), audio, sr)
    return path


def test_convert_to_mono_16k(sample_audio, tmp_path):
    output = tmp_path / "converted.wav"
    result = convert_to_mono_16k(sample_audio, output)
    assert result.exists()
    import librosa
    y, sr = librosa.load(str(result), sr=None)
    assert sr == 16000
    assert y.ndim == 1  # mono


def test_detect_intro_end(sample_audio):
    boundary = detect_intro_end(sample_audio)
    assert 2.0 <= boundary <= 6.0


def test_detect_intro_end_no_intro(tmp_path):
    sr = 16000
    audio = np.random.randn(10 * sr).astype(np.float32) * 0.2
    path = tmp_path / "no_intro.wav"
    sf.write(str(path), audio, sr)
    boundary = detect_intro_end(path)
    assert boundary == 0.0
