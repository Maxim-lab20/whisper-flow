import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from app.core.config import settings

logger = logging.getLogger(__name__)


class AudioProcessingError(Exception):
    """Raised when audio processing fails."""
    pass


class AudioService:
    """Service for processing and normalizing audio files."""

    SUPPORTED_FORMATS = set(settings.allowed_formats)

    @classmethod
    def validate_format(cls, filename: str) -> bool:
        """Check if the file format is supported."""
        ext = Path(filename).suffix.lower().lstrip(".")
        return ext in cls.SUPPORTED_FORMATS

    @classmethod
    async def normalize_for_whisper(cls, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert audio to Whisper's preferred format: 16kHz mono WAV.

        Args:
            input_path: Path to input audio file
            output_path: Optional output path (defaults to temp file)

        Returns:
            Path to normalized audio file

        Raises:
            AudioProcessingError: If conversion fails
        """
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".wav")

        try:
            logger.info(f"Normalizing audio: {input_path}")

            # Detect format and load
            audio = AudioSegment.from_file(input_path)

            # Convert to 16kHz mono
            audio = audio.set_frame_rate(settings.sample_rate)
            audio = audio.set_channels(1)

            # Export as WAV
            audio.export(output_path, format="wav")

            logger.info(f"Normalized audio saved to: {output_path}")
            return output_path

        except CouldntDecodeError as e:
            logger.error(f"Failed to decode audio: {e}")
            raise AudioProcessingError(f"Could not decode audio file: {e}")
        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            raise AudioProcessingError(f"Audio processing failed: {e}")

    @classmethod
    def get_duration(cls, file_path: str) -> float:
        """Get audio duration in seconds."""
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0

    @classmethod
    async def chunk_audio(
        cls,
        audio_path: str,
        chunk_duration_sec: int = 30,
        overlap_sec: float = 0.5,
    ) -> list[str]:
        """
        Split long audio into chunks with overlap.

        Args:
            audio_path: Path to audio file
            chunk_duration_sec: Duration of each chunk in seconds
            overlap_sec: Overlap between chunks in seconds

        Returns:
            List of paths to chunk files
        """
        audio = AudioSegment.from_file(audio_path)
        chunk_ms = chunk_duration_sec * 1000
        overlap_ms = int(overlap_sec * 1000)

        chunks = []
        temp_dir = tempfile.mkdtemp()

        start = 0
        chunk_index = 0

        while start < len(audio):
            end = min(start + chunk_ms, len(audio))
            chunk = audio[start:end]

            chunk_path = os.path.join(temp_dir, f"chunk_{chunk_index:04d}.wav")
            chunk.export(chunk_path, format="wav")
            chunks.append(chunk_path)

            start = end - overlap_ms
            chunk_index += 1

        logger.info(f"Split audio into {len(chunks)} chunks")
        return chunks


audio_service = AudioService()
