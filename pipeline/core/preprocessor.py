import subprocess
from pathlib import Path

import librosa
import numpy as np


def convert_to_mono_16k(input_path: Path, output_path: Path) -> Path:
    """Convert an audio file to 16 kHz mono WAV using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def detect_intro_end(audio_path: Path, window_sec: float = 2.0, threshold_ratio: float = 2.0) -> float:
    """Detect where the intro ends by finding a loud-to-quiet RMS energy transition."""
    y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    window_samples = int(window_sec * sr)
    n_windows = len(y) // window_samples
    if n_windows < 3:
        return 0.0
    rms_values = []
    for i in range(n_windows):
        start = i * window_samples
        end = start + window_samples
        rms = np.sqrt(np.mean(y[start:end] ** 2))
        rms_values.append(rms)
    rms_values = np.array(rms_values)
    opening_rms = rms_values[0]
    if opening_rms < 0.01:
        return 0.0
    for i in range(1, len(rms_values)):
        if rms_values[i] < opening_rms / threshold_ratio:
            return i * window_sec
    return 0.0
