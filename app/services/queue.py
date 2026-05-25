import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import settings

logger = logging.getLogger(__name__)


class JobQueue:
    """Wrapper around Redis Queue for transcription jobs."""

    def __init__(self):
        self.redis = Redis.from_url(settings.redis_url)
        self.queue = Queue("transcription", connection=self.redis)

    def enqueue(
        self,
        func,
        *args,
        job_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Enqueue a job.

        Args:
            func: Function to execute
            *args: Function arguments
            job_id: Custom job ID (generated if not provided)
            meta: Metadata to attach to job
            **kwargs: Function keyword arguments

        Returns:
            Job ID
        """
        if job_id is None:
            job_id = str(uuid.uuid4())

        job = self.queue.enqueue(
            func,
            *args,
            job_id=job_id,
            job_timeout=settings.job_timeout,
            meta=meta or {},
            **kwargs
        )

        logger.info(f"Enqueued job {job_id}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        try:
            return Job.fetch(job_id, connection=self.redis)
        except Exception as e:
            logger.warning(f"Failed to fetch job {job_id}: {e}")
            return None

    def get_status(self, job_id: str) -> str:
        """Get job status."""
        job = self.get_job(job_id)
        if job is None:
            return "unknown"
        return job.get_status()

    def get_result(self, job_id: str) -> Optional[Any]:
        """Get job result."""
        job = self.get_job(job_id)
        if job is None:
            return None
        return job.result

    def cancel(self, job_id: str) -> bool:
        """Cancel a job."""
        job = self.get_job(job_id)
        if job is None:
            return False
        job.cancel()
        return True

    def delete(self, job_id: str) -> bool:
        """Delete a job."""
        job = self.get_job(job_id)
        if job is None:
            return False
        job.delete()
        return True

    def get_queue_length(self) -> int:
        """Get number of queued jobs."""
        return len(self.queue)

    def get_worker_count(self) -> int:
        """Get number of active workers."""
        from rq.worker import Worker
        return Worker.count(queue=self.queue)

    def get_all_jobs(self, limit: int = 100) -> list[Job]:
        """Get all jobs."""
        return self.queue.get_jobs()[0:limit]


job_queue = JobQueue()
