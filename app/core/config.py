from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # API
    api_title: str = "Whisper Transcription API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Whisper
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_device: str = "cpu"  # cpu, cuda
    whisper_compute_type: str = "int8"  # int8, float16, float32

    # Audio processing
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    allowed_formats: List[str] = ["wav", "mp3", "m4a", "flac", "ogg", "wma", "aac"]
    sample_rate: int = 16000
    chunk_duration: int = 30  # seconds

    # Job processing
    job_timeout: int = 600  # seconds
    max_retries: int = 3
    retry_backoff: List[int] = [1, 2, 4, 8]  # exponential backoff in seconds

    # Storage
    storage_type: str = "local"  # local, s3
    storage_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""  # For S3-compatible services

    # Database
    database_url: str = "sqlite:///./transcription.db"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
