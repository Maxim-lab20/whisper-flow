# Whisper Transcription Pipeline

A production-ready audio transcription service built with OpenAI's Whisper, FastAPI, and Redis Queue.

## Architecture Overview

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Client    │─────▶│  FastAPI    │─────▶│   Redis     │
└─────────────┘      └─────────────┘      └─────────────┘
                            │                     │
                            │                     ▼
                            │              ┌─────────────┐
                            │              │   Worker    │
                            │              └─────────────┘
                            │                     │
                            ▼                     ▼
                     ┌─────────────┐      ┌─────────────┐
                     │ PostgreSQL  │      │   Whisper   │
                     └─────────────┘      └─────────────┘
```

### Design Decisions

#### Why Whisper?
- **Open-source & local**: No API costs, full control over scaling
- **Multilingual**: Supports 99 languages out of the box
- **Robust**: Handles accents, background noise, and overlapping speech well
- **Timestamps**: Native support for word and segment-level timestamps

#### Why FastAPI?
- **Async**: Handles concurrent connections efficiently
- **Type-safe**: Pydantic models for request/response validation
- **Auto docs**: Swagger UI and OpenAPI spec generated automatically

#### Why Redis Queue?
- **Simple**: Easy to understand and debug compared to Celery
- **Reliable**: Job persistence with Redis as backend
- **Scalable**: Workers can be horizontally scaled

#### Async Job Model
Transcription is inherently slow (seconds to minutes per audio minute). A synchronous API would timeout and block resources. Our approach:
1. Accept upload immediately → return job ID
2. Queue job for background processing
3. Client polls for status or receives webhook callback
4. Results stored and retrievable later

#### Audio Format Handling
We use **ffmpeg** for format normalization:
- Convert any input format (MP3, WAV, M4A, FLAC, etc.) to 16kHz mono PCM
- This is Whisper's native format for best accuracy
- Conversion happens before transcription to avoid CPU waste

#### Long Audio Strategy
For files exceeding Whisper's context window (~30 seconds):
1. **VAD-based chunking**: Split on silence boundaries using Voice Activity Detection
2. **Overlap padding**: 0.5s overlap prevents word truncation at boundaries
3. **Parallel processing**: Chunks transcribed concurrently where possible
4. **Timestamp reconstruction**: Merge results with adjusted timestamps

#### Failure Recovery
- **Retry with exponential backoff**: 1s → 2s → 4s → 8s (max 3 attempts)
- **Dead letter queue**: Failed jobs moved for manual inspection
- **Idempotent jobs**: Same job ID can be re-processed without duplicates
- **Health checks**: Worker pings Redis; stale jobs re-queued

## Quick Start

### Prerequisites
- Python 3.11+
- Redis server
- ffmpeg

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis
docker run -d -p 6379:6379 redis:alpine

# Run API server
uvicorn app.main:app --reload

# In another terminal, run worker
python -m app.workers.transcription_worker
```

### Docker Deployment

```bash
# Build and run all services
docker-compose up -d

# View logs
docker-compose logs -f

# Run tests
docker-compose exec api pytest
```

## API Usage

### Upload and Transcribe

```bash
curl -X POST http://localhost:8000/api/v1/transcribe \
  -F "file=@audio.mp3" \
  -F "language=en" \
  -F "model=base"
```

Response:
```json
{
  "job_id": "f7d3a8b2-4c1e-4f3a-9b2e-7c4d8e5f6a7b",
  "status": "queued",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Check Status

```bash
curl http://localhost:8000/api/v1/jobs/f7d3a8b2-4c1e-4f3a-9b2e-7c4d8e5f6a7b
```

Response:
```json
{
  "job_id": "f7d3a8b2-4c1e-4f3a-9b2e-7c4d8e5f6a7b",
  "status": "completed",
  "transcript": "Hello, this is a test transcription...",
  "segments": [
    {"text": "Hello, this is", "start": 0.0, "end": 1.2},
    {"text": " a test transcription.", "start": 1.2, "end": 2.5}
  ],
  "duration": 2.5,
  "language": "en"
}
```

## Project Structure

```
whisper-transcription/
├── app/
│   ├── api/              # API routes and handlers
│   ├── core/             # Configuration, dependencies
│   ├── models/           # Pydantic models, database schemas
│   ├── services/         # Business logic (transcription, storage)
│   └── workers/          # Background job workers
├── docker/               # Dockerfiles
├── tests/                # Integration and unit tests
├── scripts/              # Utility scripts
└── docker-compose.yml    # Local development stack
```

## Configuration

Configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `WHISPER_MODEL` | `base` | Whisper model size (tiny/base/small/medium/large) |
| `MAX_FILE_SIZE` | `100MB` | Maximum upload size |
| `ALLOWED_FORMATS` | `wav,mp3,m4a,flac,ogg` | Accepted audio formats |
| `JOB_TIMEOUT` | `600` | Job timeout in seconds |

## Scalability

- **Horizontal scaling**: Add more worker containers
- **Model caching**: First load is slow (~1s), subsequent runs are fast
- **GPU support**: Set `WHISPER_DEVICE=cuda` for GPU acceleration

## License

MIT
