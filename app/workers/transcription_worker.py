import os
import logging
from typing import Dict, Any

from app.services.transcription import transcription_service
from app.services.audio import audio_service, AudioProcessingError
from app.services.storage import storage_service
from app.core.config import settings

logger = logging.getLogger(__name__)


def process_transcription_job(job_id: str, audio_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker function to process a transcription job.

    Args:
        job_id: Unique job identifier
        audio_path: Path to the uploaded audio file
        options: Transcription options (language, model, word_timestamps, etc.)

    Returns:
        Dictionary with transcription result

    Raises:
        Exception: If transcription fails
    """
    try:
        logger.info(f"Processing job {job_id}")

        # Step 1: Normalize audio for Whisper
        normalized_path = None
        try:
            normalized_path = await_audio_service_normalize(audio_path)
        except AudioProcessingError as e:
            return {
                "status": "failed",
                "error": f"Audio processing failed: {str(e)}",
            }

        # Step 2: Transcribe
        try:
            result = await_transcription_service(
                normalized_path,
                language=options.get("language"),
                word_timestamps=options.get("word_timestamps", False),
            )

            # Convert to dict for JSON serialization
            return {
                "status": "completed",
                "result": result.model_dump(),
            }

        except Exception as e:
            logger.error(f"Transcription failed for job {job_id}: {e}")
            return {
                "status": "failed",
                "error": str(e),
            }

        finally:
            # Cleanup normalized file
            if normalized_path and os.path.exists(normalized_path):
                os.remove(normalized_path)

    except Exception as e:
        logger.exception(f"Job {job_id} failed unexpectedly")
        return {
            "status": "failed",
            "error": str(e),
        }


# Helper functions for sync/async compatibility
def await_audio_service_normalize(path: str) -> str:
    """Sync wrapper for async audio normalization."""
    import asyncio
    return asyncio.run(audio_service.normalize_for_whisper(path))


def await_transcription_service(path: str, language: str = None, word_timestamps: bool = False):
    """Sync wrapper for async transcription."""
    import asyncio
    return asyncio.run(transcription_service.transcribe(path, language, word_timestamps))


def run_worker():
    """Run the RQ worker."""
    from redis import Redis
    from rq import Worker
    from app.core.config import settings

    redis = Redis.from_url(settings.redis_url)

    with Worker(["transcription"], connection=redis) as worker:
        logger.info("Worker started, listening for jobs...")
        worker.work()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    run_worker()
