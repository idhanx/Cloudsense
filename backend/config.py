"""
CloudSense Configuration Management

Centralized configuration using environment variables.
All settings are loaded from .env file with validation.
"""

import os
import sys
from typing import List

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings

from pydantic import Field, validator


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables or .env file.
    Required settings will raise an error if not provided.
    """
    
    # ==================== Security ====================
    JWT_SECRET: str = Field(
        ...,
        description="Secret key for JWT token signing. MUST be set in .env"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithm for JWT token signing"
    )
    JWT_EXPIRATION_HOURS: int = Field(
        default=24,
        ge=1,
        le=168,  # Max 1 week
        description="JWT token expiration time in hours"
    )
    
    # ==================== Database ====================
    DATABASE_PATH: str = Field(
        default="./data/cloudsense.db",
        description="Path to SQLite database file"
    )
    
    # ==================== File Upload ====================
    UPLOAD_DIR: str = Field(
        default="./data/uploads",
        description="Directory for uploaded files"
    )
    ANALYSIS_DIR: str = Field(
        default="./data/analyses",
        description="Directory for analysis results"
    )
    MAX_UPLOAD_SIZE: int = Field(
        default=100 * 1024 * 1024,  # 100 MB
        ge=1024 * 1024,  # Min 1 MB
        le=1024 * 1024 * 1024,  # Max 1 GB
        description="Maximum file upload size in bytes"
    )
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=[".h5", ".hdf5"],
        description="Allowed file extensions for upload"
    )
    
    # ==================== CORS ====================
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:8080",
            "http://localhost:8081",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:8080",
        ],
        description="Allowed CORS origins"
    )
    
    # ==================== ML Model ====================
    MODEL_PATH: str = Field(
        default="../models/models/best_model.pth",
        description="Path to trained U-Net model"
    )
    IMG_SIZE: int = Field(
        default=512,
        ge=128,
        le=1024,
        description="Image size for model input"
    )
    DEVICE: str = Field(
        default="mps",
        description="Device for model inference (mps/cuda/cpu)"
    )
    
    # ==================== TCC Detection ====================
    BT_THRESHOLD: float = Field(
        default=218.0,
        ge=180.0,
        le=320.0,
        description="Brightness temperature threshold in Kelvin"
    )
    PIXEL_AREA_KM2: float = Field(
        default=16.0,
        gt=0,
        description="Pixel area in km² (4km x 4km)"
    )
    MIN_AREA_KM2: float = Field(
        default=34800.0,
        gt=0,
        description="Minimum TCC area in km²"
    )
    DBSCAN_EPS: float = Field(
        default=1.5,
        gt=0,
        description="DBSCAN epsilon parameter"
    )
    DBSCAN_MIN_SAMPLES: int = Field(
        default=5,
        ge=1,
        description="DBSCAN minimum samples"
    )
    
    # ==================== Tracking ====================
    MAX_TRACK_DISTANCE_KM: float = Field(
        default=200.0,
        gt=0,
        description="Maximum track distance in km"
    )
    TRACK_LOST_THRESHOLD: int = Field(
        default=3,
        ge=1,
        description="Frames before track is lost"
    )
    
    # ==================== Validators ====================
    
    @validator("JWT_SECRET")
    def validate_jwt_secret(cls, v):
        """Ensure JWT secret is strong enough."""
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 characters long. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return v
    
    @validator("DATABASE_PATH", "UPLOAD_DIR", "ANALYSIS_DIR")
    def validate_paths(cls, v):
        """Ensure parent directories exist."""
        parent = os.path.dirname(v)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        return v
    
    @validator("MODEL_PATH")
    def validate_model_path(cls, v):
        """Check if model file exists."""
        # Try multiple possible locations
        possible_paths = [
            v,
            os.path.join(os.path.dirname(__file__), v),
            "../models/models/best_model.pth",
            "../training/models/best_model.pth",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Model not found - log warning but don't fail
        # (allows app to start even if model is missing)
        print(f"⚠️  WARNING: Model not found at {v}")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars


# ==================== Initialize Settings ====================

try:
    settings = Settings()
    print("✅ Configuration loaded successfully")
except Exception as e:
    print(f"❌ Configuration error: {e}")
    print("\n💡 Make sure you have a .env file with required settings:")
    print("   JWT_SECRET=<your-secret-key>")
    print("\nGenerate a secure JWT_SECRET with:")
    print('   python -c "import secrets; print(secrets.token_urlsafe(64))"')
    sys.exit(1)


# ==================== Create Required Directories ====================

try:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.ANALYSIS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)
    print(f"✅ Directories created: {settings.UPLOAD_DIR}, {settings.ANALYSIS_DIR}")
except Exception as e:
    print(f"⚠️  Warning: Could not create directories: {e}")

