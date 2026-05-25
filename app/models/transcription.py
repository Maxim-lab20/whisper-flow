from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TranscriptSegment(BaseModel):
    text: str
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    confidence: Optional[float] = Field(None, ge=0, le=1)


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    confidence: Optional[float] = None


class TranscriptionResult(BaseModel):
    text: str
    language: str
    duration: float
    segments: List[TranscriptSegment]
    words: Optional[List[WordTimestamp]] = None


class JobCreate(BaseModel):
    language: Optional[str] = Field(None, description="ISO 639-1 language code")
    model: Optional[str] = Field("base", description="Whisper model size")
    word_timestamps: bool = Field(False, description="Include word-level timestamps")
    callback_url: Optional[str] = Field(None, description="Webhook URL for completion notification")


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[TranscriptionResult] = None


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
    workers: int
    queued_jobs: int
