"""
CloudSense — Centralized Configuration
All settings loaded from environment variables. No hardcoded secrets.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings from environment variables."""

    # ── Security ──
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))

    # ── Google OAuth ──
    GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")

    # ── Database ──
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cloudsense.db')}"
    )

    # ── CORS ──
    CORS_ORIGINS: list = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173"
        ).split(",")
    ]

    # ── Paths ──
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    UPLOAD_DIR: str = os.path.join(BASE_DIR, "uploads")
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "output")
    MODEL_PATH: str = os.environ.get(
        "MODEL_PATH",
        os.path.join(os.path.dirname(BASE_DIR), "model", "best_model.pth"),
    )
    MOSDAC_DATA_DIR: str = os.path.join(
        os.path.dirname(BASE_DIR), "dataset", "MOSDAC_Data"
    )

    # ── Upload limits ──
    MAX_UPLOAD_SIZE_MB: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "500"))
    ALLOWED_EXTENSIONS: set = {".h5", ".hdf5", ".png", ".jpg", ".jpeg"}

    # ── Rate Limiting ──
    RATE_LIMIT_PER_MINUTE: int = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))

    @classmethod
    def validate(cls):
        """Validate required settings on startup."""
        if not cls.JWT_SECRET or len(cls.JWT_SECRET) < 32:
            raise ValueError(
                "JWT_SECRET must be set and >= 32 characters. "
                'Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
        os.makedirs(cls.MOSDAC_DATA_DIR, exist_ok=True)


settings = Settings()
