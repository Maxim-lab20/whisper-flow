# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Local Development
```bash
# Quick setup (creates venv, installs deps)
./scripts/dev.sh

# Start API server
uvicorn app.main:app --reload

# Start worker (separate terminal)
python -m app.workers.transcription_worker

# Start Redis (if not using Docker)
docker run -d -p 6379:6379 redis:alpine
```

### Docker
```bash
# Full stack (Redis + API + Workers)
docker-compose up -d

# View logs
docker-compose logs -f [api|worker|redis]

# Stop all services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py

# Run with coverage
pytest --cov=app

# Run tests in Docker
docker-compose exec api pytest
```

### Client Testing
```bash
# Transcribe a file
python scripts/example_client.py transcribe audio.wav

# List all jobs
python scripts/example_client.py list

# Check API health
python scripts/example_client.py health
```

## Architecture

This is an **async job-based transcription service**. The key architectural pattern:

1. **API accepts upload** → saves file to disk, returns `job_id` immediately
2. **RQ queues the job** → workers pick up jobs from Redis
3. **Worker processes** → normalizes audio (ffmpeg) → transcribes (Whisper) → stores result
4. **Client polls** → `GET /jobs/{id}` returns status/result when complete

### Service Layer Separation

```
app/api/           # FastAPI routes (thin layer, just HTTP handling)
app/services/      # Business logic (transcription, storage, audio, queue)
app/workers/       # RQ worker entry points
app/models/        # Pydantic models for request/response validation
app/core/          # Configuration via pydantic-settings
```

**Key**: Routes in `app/api/` don't contain business logic—they delegate to services. Workers call the same services as the API would.

### Async/Sync Boundary

- **API is async** (FastAPI `async def`)
- **Workers are sync** (RQ runs in thread pool)
- **Services have both**: Methods are `async def`, workers wrap them with `asyncio.run()`

When modifying services: if adding methods called by workers, ensure they're awaitable or provide sync wrappers.

### Job Flow

1. `POST /transcribe` → `app/api/transcription.py:create_transcription_job()`
2. Saves file via `storage_service.save_upload()`
3. Enqueues `process_transcription_job()` via `job_queue.enqueue()`
4. Worker picks up job → calls `process_transcription_job()` in `app/workers/transcription_worker.py`
5. Job normalizes audio → transcribes → returns dict with `status` and `result`/`error`
6. RQ stores result in Redis; API retrieves it via `job_queue.get_job()`

### Status Mapping

RQ statuses → API statuses:
- `queued` → `JobStatus.queued`
- `started` → `JobStatus.processing`
- `finished` → `JobStatus.completed` OR `JobStatus.failed` (check `result["status"]`)
- `failed` → `JobStatus.failed`

## Configuration

All config via environment variables or `.env` file. See `app/core/config.py` and `.env.example`.

**Important defaults**:
- `WHISPER_MODEL=base` — First load downloads ~150MB to `storage/models/`
- `MAX_FILE_SIZE=100MB` — Bytes, not MB
- `REDIS_URL=redis://localhost:6379/0` — Must be reachable from both API and workers
- `STORAGE_PATH=./storage` — Audio files and cached models

## Key Patterns

### Singleton Services
Services in `app/services/` export singleton instances (`transcription_service`, `storage_service`, etc.). Import these directly—don't instantiate.

### Lazy Model Loading
Whisper model loads on first use (`TranscriptionService.model` property). First transcription is slow (~1-2s), subsequent calls are fast.

### Audio Normalization
All audio is normalized to 16kHz mono WAV before transcription. This happens in `AudioService.normalize_for_whisper()`. Original file is preserved; normalized version is temp file deleted after transcription.

### Error Handling in Workers
Workers return dicts with `{"status": "completed"|"failed", "result": ..., "error": ...}`. They don't raise exceptions—exceptions are caught and converted to failed status. This ensures jobs complete with observable errors rather than silently failing.

## Gotchas

1. **Workers need async wrappers**: RQ is sync, services are async. Use `asyncio.run()` or the wrapper pattern in `transcription_worker.py`.

2. **Shared storage required**: API saves files, workers read them. In Docker, both mount `./storage:/app/storage`. In distributed setups, use S3 or NFS.

3. **Model cache is local**: Each worker downloads its own model cache. For many workers, pre-seed `storage/models/` or use shared volume.

4. **Job results not persisted**: RQ keeps results in Redis (configurable TTL). For persistence, store transcripts in database (not implemented).

5. **RQ job TTL**: Results expire after default TTL (500s). Adjust via `result_ttl` in `job_queue.enqueue()` if jobs take longer.

## Adding Features

### New API Endpoint
1. Add Pydantic models to `app/models/transcription.py`
2. Add route to `app/api/transcription.py` or create new router file
3. Include router in `app/main.py:create_app()`

### New Worker Job Type
1. Create worker function (sync) that returns a dict
2. Enqueue via `job_queue.enqueue(your_function, args, job_id=id)`
3. Workers will pick it up if listening on the same queue name

### Change Transcription Behavior
Modify `TranscriptionService.transcribe()` in `app/services/transcription.py`. For model changes, restart workers—they don't reload automatically.

## Storage Backends

Current: Local filesystem (`./storage/audio/`).

To switch to S3:
1. Set `STORAGE_TYPE=s3` and `S3_BUCKET=...` in `.env`
2. Implement S3 methods in `storage_service` (hooks exist but not implemented)
3. Ensure workers have IAM credentials to access bucket
