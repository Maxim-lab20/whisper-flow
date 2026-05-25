import pytest
from fastapi.testclient import TestClient
from io import BytesIO

from app.main import create_app


@pytest.fixture
def client():
    """Test client for the API."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_audio():
    """Sample audio file for testing."""
    # In real tests, use actual audio file
    audio_content = b"fake audio content"
    return BytesIO(audio_content)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "workers" in data
        assert "queued_jobs" in data


class TestTranscriptionAPI:
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_transcribe_missing_file(self, client):
        response = client.post("/api/v1/transcribe")
        assert response.status_code == 422  # Validation error

    def test_transcribe_unsupported_format(self, client):
        files = {"file": ("test.txt", BytesIO(b"text content"), "text/plain")}
        response = client.post("/api/v1/transcribe", files=files)
        assert response.status_code == 415

    def test_get_nonexistent_job(self, client):
        response = client.get("/api/v1/jobs/nonexistent-id")
        assert response.status_code == 404

    def test_list_jobs(self, client):
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert "page" in data
