import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storing and retrieving audio files."""

    def __init__(self):
        self.storage_path = Path(settings.storage_path)
        self.audio_path = self.storage_path / "audio"
        self.audio_path.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, filename: str, content: bytes, job_id: str) -> str:
        """
        Save an uploaded audio file.

        Args:
            filename: Original filename
            content: File content bytes
            job_id: Unique job identifier

        Returns:
            Path to the saved file
        """
        # Get file extension
        ext = Path(filename).suffix.lower()
        if not ext:
            ext = ".wav"  # Default

        # Create unique filename
        safe_filename = f"{job_id}{ext}"
        file_path = self.audio_path / safe_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved audio file: {file_path}")
        return str(file_path)

    def get_path(self, job_id: str, extension: str = ".wav") -> str:
        """Get the storage path for a job's audio file."""
        return str(self.audio_path / f"{job_id}{extension}")

    async def delete(self, job_id: str, extension: str = ".wav") -> bool:
        """Delete a stored audio file."""
        file_path = self.audio_path / f"{job_id}{extension}"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted audio file: {file_path}")
            return True
        return False

    async def cleanup(self, older_than_hours: int = 24):
        """Delete audio files older than specified hours."""
        import time

        cutoff = time.time() - (older_than_hours * 3600)
        deleted = 0

        for file_path in self.audio_path.iterdir():
            if file_path.stat().st_mtime < cutoff:
                file_path.unlink()
                deleted += 1

        logger.info(f"Cleaned up {deleted} old audio files")
        return deleted


storage_service = StorageService()
