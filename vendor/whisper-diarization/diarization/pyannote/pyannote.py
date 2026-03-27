import os
from typing import Union

import torch

from pyannote.audio import Pipeline


class PyannoteDiarizer:
    """Speaker diarization using pyannote.audio 3.1.

    Same interface as MSDDDiarizer / SortformerDiarizer:
        diarize(audio: Tensor) -> list[tuple[int, int, int]]
    """

    def __init__(self, device: Union[str, torch.device], hf_token: str | None = None):
        token = hf_token or os.environ.get("HF_TOKEN")
        if not token:
            raise ValueError(
                "Pyannote 3.1 requires a HuggingFace token. "
                "Pass --hf-token or set HF_TOKEN env var. "
                "Accept the license at https://huggingface.co/pyannote/speaker-diarization-3.1"
            )

        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        self.pipeline.to(torch.device(device))

    def diarize(self, audio: torch.Tensor) -> list[tuple[int, int, int]]:
        """Run diarization on audio tensor.

        Args:
            audio: shape (1, num_samples) at 16kHz, float values in [-1, 1]

        Returns:
            Sorted list of (start_ms, end_ms, speaker_id) tuples.
        """
        diarization = self.pipeline({"waveform": audio, "sample_rate": 16000})

        # Map pyannote speaker labels (e.g. "SPEAKER_00") to integer IDs
        speaker_map: dict[str, int] = {}
        labels: list[tuple[int, int, int]] = []

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_map:
                speaker_map[speaker] = len(speaker_map)
            start_ms = int(turn.start * 1000)
            end_ms = int(turn.end * 1000)
            labels.append((start_ms, end_ms, speaker_map[speaker]))

        labels.sort(key=lambda x: x[0])
        return labels
