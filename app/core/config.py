"""Auralis Configuration Settings.

Provides environment variable overrides, strict path typing, and configurable
concurrency defaults.
"""

import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        """Application settings with environment variable auto-binding."""

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # Core Application
        APP_ENV: str = "development"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000

        # Concurrency & Worker Limits (Conservative default: 4 workers)
        MAX_CONCURRENT_WORKERS: int = 4

        # Storage & Lifecycles
        TEMP_DIR: Path = Path("data/temp")
        COMPLETED_DIR: Path = Path("data/completed")
        JOB_TTL_MINUTES: int = 60
        DISK_FREE_THRESHOLD_MB: int = 2048

        # Security & Abuse Mitigation
        MAX_PLAYLIST_ITEMS: int = 100
        RATE_LIMIT_PER_MINUTE: int = 10

        # Database
        DB_PATH: Path = Path("data/auralis.db")

        # Optional explicit FFmpeg executable override
        FFMPEG_PATH: str | None = None

        def ensure_directories(self) -> None:
            """Ensures all necessary local storage directories exist."""
            self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self.COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
            self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

except ImportError:
    # Standard library fallback if pydantic_settings is not yet installed
    class Settings:  # type: ignore[no-redef]
        """Fallback settings implementation using os.environ."""

        def __init__(self) -> None:
            self.APP_ENV: str = os.getenv("APP_ENV", "development")
            self.DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")
            self.HOST: str = os.getenv("HOST", "0.0.0.0")
            self.PORT: int = int(os.getenv("PORT", "8000"))

            self.MAX_CONCURRENT_WORKERS: int = int(os.getenv("MAX_CONCURRENT_WORKERS", "4"))

            self.TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "data/temp"))
            self.COMPLETED_DIR: Path = Path(os.getenv("COMPLETED_DIR", "data/completed"))
            self.JOB_TTL_MINUTES: int = int(os.getenv("JOB_TTL_MINUTES", "60"))
            self.DISK_FREE_THRESHOLD_MB: int = int(os.getenv("DISK_FREE_THRESHOLD_MB", "2048"))

            self.MAX_PLAYLIST_ITEMS: int = int(os.getenv("MAX_PLAYLIST_ITEMS", "100"))
            self.RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

            self.DB_PATH: Path = Path(os.getenv("DB_PATH", "data/auralis.db"))
            self.FFMPEG_PATH: str | None = os.getenv("FFMPEG_PATH")

        def ensure_directories(self) -> None:
            """Ensures all necessary local storage directories exist."""
            self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self.COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
            self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
