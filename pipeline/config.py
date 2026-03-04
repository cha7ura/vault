from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Paths
    data_dir: Path = Path(__file__).parent.parent / "data"
    db_url: str = ""

    # LM Studio
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "default"

    # Pipeline defaults
    audio_sample_rate: int = 16000
    default_whisper_model: str = "medium.en"
    default_diarizer: str = "whisper-diarization"

    model_config = {"env_prefix": "VAULT_", "env_file": ".env"}

    def model_post_init(self, __context) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "audio").mkdir(exist_ok=True)
        (self.data_dir / "transcripts").mkdir(exist_ok=True)
        if not self.db_url:
            self.db_url = f"sqlite:///{self.data_dir / 'vault.db'}"


settings = Settings()
