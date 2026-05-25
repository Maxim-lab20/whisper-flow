import os
import tempfile
import logging
from typing import Optional, List
from pathlib import Path

from faster_whisper import WhisperModel
import torch

from app.core.config import settings
from app.models.transcription import TranscriptionResult, TranscriptSegment, WordTimestamp

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for transcribing audio using Whisper."""

    def __init__(self):
        self._model: Optional[WhisperModel] = None

    @property
    def model(self) -> WhisperModel:
        """Lazy-load the Whisper model."""
        if self._model is None:
            logger.info(f"Loading Whisper model: {settings.whisper_model}")
            device = "cuda" if settings.whisper_device == "cuda" and torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else settings.whisper_compute_type

            self._model = WhisperModel(
                settings.whisper_model,
                device=device,
                compute_type=compute_type,
                download_root=os.path.join(settings.storage_path, "models"),
            )
            logger.info(f"Whisper model loaded on {device}")
        return self._model

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file
            language: ISO 639-1 language code (auto-detect if None)
            word_timestamps: Whether to include word-level timestamps

        Returns:
            TranscriptionResult with text, segments, and metadata
        """
        logger.info(f"Transcribing {audio_path} (language={language}, word_timestamps={word_timestamps})")

        # faster_whisper handles long files automatically with chunking
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=word_timestamps,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        result_segments = []
        result_words = []

        for segment in segments:
            result_segments.append(
                TranscriptSegment(
                    text=segment.text.strip(),
                    start=segment.start,
                    end=segment.end,
                    confidence=segment.avg_logprob,
                )
            )

            if word_timestamps and segment.words:
                for word in segment.words:
                    result_words.append(
                        WordTimestamp(
                            word=word.word,
                            start=word.start,
                            end=word.end,
                        )
                    )

        return TranscriptionResult(
            text="".join(s.text for s in result_segments),
            language=info.language,
            duration=info.duration,
            segments=result_segments,
            words=result_words if word_timestamps else None,
        )


# Singleton instance
transcription_service = TranscriptionService()
