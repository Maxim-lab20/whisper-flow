# Design Decisions - Whisper Transcription Pipeline

This document explains the key architectural and technical decisions made when building the transcription service.

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Architecture Pattern](#architecture-pattern)
3. [Audio Processing Strategy](#audio-processing-strategy)
4. [Scalability Approach](#scalability-approach)
5. [Error Handling & Reliability](#error-handling--reliability)
6. [API Design](#api-design)
7. [Storage Strategy](#storage-strategy)
8. [Performance Optimizations](#performance-optimizations)
9. [Trade-offs & Future Improvements](#trade-offs--future-improvements)

---

## Technology Stack

### Why Whisper over other STT engines?

| Factor | Whisper | Google Cloud STT | AWS Transcribe | Azure Speech |
|--------|---------|------------------|----------------|--------------|
| Cost | Free (local) | $0.024/min | $0.024/min | $1/hour |
| Privacy | On-prem | Cloud-only | Cloud-only | Cloud-only |
| Languages | 99 | 125 | 100 | 100+ |
| Latency | Low (local) | Medium (network) | Medium (network) | Medium (network) |
| Timestamps | Native | Yes | Yes | Yes |

**Decision**: Whisper wins on cost, privacy, and simplicity. No API keys, no rate limits, no network dependency. The `faster-whisper` implementation provides 4x speedup over the original while maintaining accuracy.

### Why FastAPI?

- **Async/await**: Handles concurrent uploads without threading complexity
- **Auto-validation**: Pydantic catches bad requests before they reach business logic
- **OpenAPI**: Swagger docs generated for free—great for API consumers
- **Type safety**: Mypy compatibility catches bugs at development time

### Why Redis Queue over Celery?

| Feature | RQ | Celery |
|---------|----|----|
| Complexity | Simple | Complex |
| Broker | Redis only | Redis, RabbitMQ, SQS, etc. |
| Monitoring | Built-in UI | Requires Flower |
| Learning curve | Low | High |

**Decision**: RQ is sufficient for our use case. Celery's extra features (routing, chains, chords) aren't needed for a single-purpose transcription pipeline.

---

## Architecture Pattern

### Asynchronous Job Model

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Client  │────▶│   API   │────▶│  Queue  │────▶│ Worker  │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
                      │                                 │
                      ▼                                 ▼
                ┌─────────┐                     ┌─────────┐
                │ Storage │                     │ Whisper │
                └─────────┘                     └─────────┘
```

**Why not synchronous transcription?**

1. **Timeout risk**: A 10-minute audio file takes ~2 minutes to transcribe. HTTP requests timeout after 30-60s
2. **Resource blocking**: Synchronous processing ties up a worker while waiting for I/O
3. **Poor UX**: Users stare at a loading spinner with no progress indication

**Why not websockets?**

Websockets add complexity. For a job that takes 30s-5min, polling every 1-2s is perfectly adequate and works everywhere (curl, browsers, mobile SDKs).

---

## Audio Processing Strategy

### Format Normalization with ffmpeg

**Problem**: Whisper expects 16kHz mono WAV. Users upload MP3, M4A, FLAC, etc.

**Solution**: Pre-process all audio with ffmpeg/pydub before transcription.

```python
audio = AudioSegment.from_file(input_path)
audio = audio.set_frame_rate(16000)  # Whisper's preferred sample rate
audio = audio.set_channels(1)        # Mono for consistency
audio.export(output_path, format="wav")
```

**Trade-off**: Conversion takes 5-10% of total processing time, but ensures 100% format compatibility and improves accuracy.

### Handling Long Audio

**Whisper's context window**: ~30 seconds of audio per inference pass.

**Strategies evaluated**:

1. **Chunk on silence** (VAD): Split at natural pauses
   - ✅ Pros: Doesn't cut words mid-sentence
   - ❌ Cons: Requires VAD model; adds latency

2. **Fixed-size chunks with overlap**: Split every 30s with 0.5s overlap
   - ✅ Pros: Simple, deterministic
   - ✅ Pros: Overlap prevents word truncation
   - ✅ Pros: Parallelizable
   - ❌ Cons: May break at awkward sentence boundaries

**Decision**: `faster-whisper` implements chunking internally with VAD. We rely on its built-in handling rather than re-implementing.

---

## Scalability Approach

### Vertical Scaling (Single Machine)

- **GPU**: Set `WHISPER_DEVICE=cuda` for 5-10x speedup
- **Model size**: `tiny` (fastest) → `large` (most accurate)
- **Worker processes**: Match CPU core count (each worker uses 1 core)

### Horizontal Scaling (Multiple Machines)

```yaml
# docker-compose.yml
worker:
  deploy:
    replicas: 4  # 4 parallel jobs
```

**Bottleneck analysis**:

| Component | Bottleneck | Scaling method |
|-----------|-----------|----------------|
| API server | Network I/O | Add more replicas |
| Redis | Memory | Use Redis Cluster |
| Worker | CPU/GPU | Add more workers |
| Storage | Disk I/O | Use network storage (NFS/S3) |

**Cost optimization**: Run 2-3 workers with `base` model rather than 1 worker with `large` model. Throughput is higher and cost per transcription is lower.

---

## Error Handling & Reliability

### Retry Strategy

```python
retry_backoff = [1, 2, 4, 8]  # Exponential backoff in seconds
max_retries = 3
```

**What can fail?**

| Failure type | Retryable? | Action |
|--------------|------------|--------|
| Network blip | ✅ Yes | Retry |
| Worker crash | ✅ Yes | Job re-queued by RQ |
| Corrupt audio | ❌ No | Fail fast, notify user |
| OOM (large file) | ❌ No | Fail, suggest chunking |

### Idempotency

Jobs are keyed by `job_id`. Re-queuing the same ID doesn't create duplicates—it just re-processes. This is crucial for recovery.

### Dead Letter Queue

After 3 failed attempts, jobs stay in Redis with `failed` status. An admin can:

```bash
# Inspect failed job
rq info
rq requeue all  # Re-queue failed jobs
```

---

## API Design

### Why REST over GraphQL?

- Simpler for a single-purpose service
- Better caching with HTTP semantics
- Easier to test with curl/Postman

### Polling vs Webhooks

**Polling** (current):
- ✅ Works everywhere (even behind firewalls)
- ✅ Simple client implementation
- ✅ No auth complexity for callbacks

**Webhooks** (future):
- ✅ Faster notification (no polling overhead)
- ❌ Client needs publicly accessible endpoint
- ❌ Auth headers require management

**Hybrid approach**: Support both. Client opts in via `callback_url` parameter.

---

## Storage Strategy

### Current: Local Filesystem

```python
storage_path/
├── audio/           # Uploaded files
└── models/          # Cached Whisper models
```

**Pros**: Simple, no external dependencies
**Cons**: Not shared across workers, disk fills up

### Production: S3-compatible Storage

```python
# Configuration change only
STORAGE_TYPE=s3
S3_BUCKET=transcription-audio
S3_ENDPOINT_URL=https://s3.amazonaws.com
```

**Pros**: Shared storage, infinite scale, lifecycle policies
**Cons**: Network latency, S3 costs

### Transcript Storage

Transcripts are small (KB scale). Options:

1. **Return only, don't persist**: Current implementation. Client saves result.
2. **Database**: Store metadata + transcript in PostgreSQL
3. **Search index**: Elasticsearch for full-text search

**Recommendation**: Start with #1, add #2 when auditing is needed, add #3 when search becomes a requirement.

---

## Performance Optimizations

### Model Caching

First load downloads ~150MB (base model). Subsequent loads use cached copy.

```python
download_root=os.path.join(settings.storage_path, "models")
```

### Faster-Whisper

Uses CTranslate2 engine instead of PyTorch:

- 4x faster inference
- Lower memory usage
- Same accuracy

### Batch Processing (Not Implemented)

For high-volume scenarios, batch multiple audio files into one Whisper call. This reduces overhead but complicates the API—omitted for v1.

---

## Trade-offs & Future Improvements

### What we optimized for

- **Simplicity**: Easy to understand, deploy, and debug
- **Cost efficiency**: No cloud API fees
- **Privacy**: Data never leaves your infrastructure

### What we sacrificed

- **Streaming transcription**: Not supported (requires full file)
- **Real-time**: Latency is seconds to minutes, not milliseconds
- **Diarization**: Can't identify different speakers (Whisper doesn't support it)

### Future Improvements

| Feature | Effort | Impact |
|---------|--------|--------|
| GPU support | Low | High (5-10x faster) |
| S3 storage | Low | Medium (scale out) |
| Webhooks | Medium | Medium (better UX) |
| Speaker diarization | High | High (new capability) |
| Streaming input | High | High (real-time use cases) |

---

## Summary

This architecture prioritizes:

1. **Reliability**: Jobs don't get lost; failures are observable
2. **Simplicity**: Small codebase, easy to onboard new developers
3. **Cost-efficiency**: No per-minute API charges
4. **Flexibility**: Swap components (storage, queue) without rewriting core logic

For a team of 1-5 engineers handling up to 1000 transcriptions per day, this design is sufficient. Beyond that, consider:
- Dedicated Redis instance
- GPU workers for faster processing
- Kafka instead of Redis Queue for better throughput
- Microservices split (API separate from workers)
