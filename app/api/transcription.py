import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse

from app.models.transcription import (
    JobCreate,
    JobResponse,
    JobStatus,
    JobListResponse,
    HealthResponse,
)
from app.services.queue import job_queue
from app.services.storage import storage_service
from app.services.audio import audio_service, AudioProcessingError
from app.workers.transcription_worker import process_transcription_job
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/transcribe", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_transcription_job(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: Optional[str] = Form(None, description="ISO 639-1 language code (auto-detect if empty)"),
    model: Optional[str] = Form("base", description="Whisper model size"),
    word_timestamps: bool = Form(False, description="Include word-level timestamps"),
    callback_url: Optional[str] = Form(None, description="Webhook URL for completion notification"),
):
    """
    Upload an audio file and create a transcription job.

    The job is processed asynchronously. Use the returned job_id to check status.
    """
    # Validate file size
    content = await file.read()
    if len(content) > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {settings.max_file_size / 1024 / 1024}MB",
        )

    # Validate file format
    if not audio_service.validate_format(file.filename):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format. Allowed: {', '.join(settings.allowed_formats)}",
        )

    # Create job
    import uuid
    job_id = str(uuid.uuid4())

    # Save uploaded file
    audio_path = await storage_service.save_upload(file.filename, content, job_id)

    # Enqueue job
    options = {
        "language": language,
        "model": model,
        "word_timestamps": word_timestamps,
        "callback_url": callback_url,
    }

    try:
        job_queue.enqueue(
            process_transcription_job,
            job_id,
            audio_path,
            options,
            job_id=job_id,
        )
    except Exception as e:
        # Cleanup if job fails to enqueue
        await storage_service.delete(job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue job: {str(e)}",
        )

    return JobResponse(
        job_id=job_id,
        status=JobStatus.queued,
        created_at=datetime.utcnow(),
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get the status and result of a transcription job."""
    job = job_queue.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Map RQ status to our status
    status_mapping = {
        "queued": JobStatus.queued,
        "started": JobStatus.processing,
        "finished": JobStatus.completed,
        "failed": JobStatus.failed,
    }

    job_status = status_mapping.get(job.get_status(), JobStatus.queued)

    response = JobResponse(
        job_id=job_id,
        status=job_status,
        created_at=datetime.fromtimestamp(job.created_at),
        updated_at=datetime.fromtimestamp(job.enqueued_at) if job.enqueued_at else None,
    )

    # Include result if completed
    if job_status == JobStatus.completed and job.result:
        if job.result.get("status") == "completed":
            from app.models.transcription import TranscriptionResult
            response.result = TranscriptionResult(**job.result["result"])
        else:
            response.status = JobStatus.failed
            response.error = job.result.get("error", "Unknown error")
    elif job_status == JobStatus.failed:
        response.error = str(job.exc_info) if job.exc_info else "Unknown error"

    return response


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_or_delete_job(job_id: str):
    """Cancel a queued job or delete job data."""
    job = job_queue.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Cancel if queued, otherwise just delete
    if job.get_status() == "queued":
        job_queue.cancel(job_id)

    job_queue.delete(job_id)
    await storage_service.delete(job_id)

    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(page: int = 1, page_size: int = 20):
    """List all transcription jobs."""
    if page_size > 100:
        page_size = 100

    all_jobs = job_queue.get_all_jobs(limit=page_size * page)

    # Convert to response format
    jobs = []
    for job in all_jobs:
        status_mapping = {
            "queued": JobStatus.queued,
            "started": JobStatus.processing,
            "finished": JobStatus.completed,
            "failed": JobStatus.failed,
        }

        jobs.append(
            JobResponse(
                job_id=job.id,
                status=status_mapping.get(job.get_status(), JobStatus.queued),
                created_at=datetime.fromtimestamp(job.created_at),
            )
        )

    # Paginate
    start = (page - 1) * page_size
    end = start + page_size
    paginated_jobs = jobs[start:end]

    return JobListResponse(
        jobs=paginated_jobs,
        total=len(jobs),
        page=page,
        page_size=page_size,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.api_version,
        workers=job_queue.get_worker_count(),
        queued_jobs=job_queue.get_queue_length(),
    )
