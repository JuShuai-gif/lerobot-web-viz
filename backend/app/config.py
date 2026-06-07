import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    dataset_path: Path = Field(default=Path("."), alias="LEROBOT_DATASET_PATH")
    repo_id: str | None = Field(default=None, alias="LEROBOT_REPO_ID")
    preload_frames: int = Field(default=1, alias="LEROBOT_PRELOAD_FRAMES")
    frame_cache_size: int = Field(default=512, alias="LEROBOT_FRAME_CACHE_SIZE")
    default_jpeg_quality: int = Field(default=80, alias="LEROBOT_JPEG_QUALITY")
    timestamp_gap_ratio: float = Field(default=1.75, alias="LEROBOT_TIMESTAMP_GAP_RATIO")
    action_jump_zscore: float = Field(default=6.0, alias="LEROBOT_ACTION_JUMP_ZSCORE")
    min_episode_frames: int = Field(default=5, alias="LEROBOT_MIN_EPISODE_FRAMES")
    cors_origins: str = Field(default="*", alias="LEROBOT_CORS_ORIGINS")
    browse_roots: str = Field(default="", alias="LEROBOT_BROWSE_ROOTS")

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_browse_roots(self) -> list[Path]:
        configured = [item.strip() for item in self.browse_roots.split(":") if item.strip()]
        candidates = configured or [str(self.dataset_path), "/data", "/home", str(Path.cwd())]
        roots: list[Path] = []
        for item in candidates:
            path = Path(item).expanduser().resolve()
            if path.exists() and path.is_dir() and path not in roots:
                roots.append(path)
        return roots

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if "LEROBOT_DATASET_PATH" not in os.environ:
        settings.dataset_path = Path(".").resolve()
    return settings
