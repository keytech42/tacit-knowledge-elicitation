# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest", "httpx"]
# ///
"""
Integration tests for the embedding Docker Compose service.

These tests require the embedding service to be running:
  make embed-download && make up-embed

In CI, the service is started by the embedding-integration job.

Run: uv run --with pytest --with httpx pytest tests/test_embedding_integration.py -xvs
"""

import os
import subprocess
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
EMBEDDING_URL = os.environ.get("EMBEDDING_URL", "http://localhost:8090")


def _embedding_reachable() -> bool:
    try:
        r = httpx.get(f"{EMBEDDING_URL}/health", timeout=5)
        return r.status_code == 200
    except httpx.ConnectError:
        return False


def _model_path() -> Path:
    model_dir = os.environ.get("EMBEDDING_MODEL_DIR", str(ROOT / "models"))
    model_file = os.environ.get("EMBEDDING_MODEL_FILE", "bge-m3-q8_0.gguf")
    return Path(model_dir) / model_file


skip_if_no_model = pytest.mark.skipif(
    not _model_path().is_file(),
    reason=f"Model file not found at {_model_path()}. Run 'make embed-download'.",
)

skip_if_no_embedding = pytest.mark.skipif(
    not _embedding_reachable(),
    reason=f"Embedding service not reachable at {EMBEDDING_URL}",
)


# ---------------------------------------------------------------------------
# Model file validation (requires download)
# ---------------------------------------------------------------------------


@skip_if_no_model
class TestModelFile:
    """Validate the downloaded GGUF model file."""

    def test_model_file_exists(self):
        assert _model_path().is_file()

    def test_model_file_is_valid_gguf(self):
        """The downloaded file should be a valid GGUF (check magic bytes)."""
        with open(_model_path(), "rb") as f:
            magic = f.read(4)
        # GGUF magic: "GGUF" (0x46475547 little-endian)
        assert magic == b"GGUF", f"Invalid GGUF magic bytes: {magic!r}"

    def test_model_file_size_is_reasonable(self):
        """bge-m3 Q8_0 should be ~605MB."""
        size_mb = _model_path().stat().st_size / (1024 * 1024)
        assert 500 < size_mb < 700, f"Unexpected model size: {size_mb:.0f}MB"


# ---------------------------------------------------------------------------
# Embedding service health
# ---------------------------------------------------------------------------


@skip_if_no_embedding
class TestEmbeddingServiceHealth:
    """Embedding service is running and responding."""

    def test_health_endpoint(self):
        r = httpx.get(f"{EMBEDDING_URL}/health", timeout=10)
        assert r.status_code == 200

    def test_make_embed_status(self):
        """'make embed-status' should report healthy."""
        result = subprocess.run(
            ["make", "embed-status"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert "healthy" in result.stdout.lower() or result.returncode == 0


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


@skip_if_no_embedding
class TestEmbeddingGeneration:
    """The embedding endpoint returns correct vectors."""

    def test_single_embedding_returns_1024_dimensions(self):
        r = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": "test query", "model": "bge-m3"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        embedding = data["data"][0]["embedding"]
        assert len(embedding) == 1024

    def test_batch_embedding(self):
        r = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={
                "input": ["first document", "second document", "third document"],
                "model": "bge-m3",
            },
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["data"]) == 3
        for item in data["data"]:
            assert len(item["embedding"]) == 1024

    def test_embedding_values_are_floats(self):
        r = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": "type check", "model": "bge-m3"},
            timeout=30,
        )
        embedding = r.json()["data"][0]["embedding"]
        assert all(isinstance(v, float) for v in embedding)

    def test_different_inputs_produce_different_embeddings(self):
        r = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": ["cats are great", "quantum mechanics"], "model": "bge-m3"},
            timeout=30,
        )
        data = r.json()["data"]
        emb_a = data[0]["embedding"]
        emb_b = data[1]["embedding"]
        assert emb_a != emb_b

    def test_same_input_produces_deterministic_embeddings(self):
        text = "deterministic embedding test"
        r1 = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": text, "model": "bge-m3"},
            timeout=30,
        )
        r2 = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": text, "model": "bge-m3"},
            timeout=30,
        )
        emb1 = r1.json()["data"][0]["embedding"]
        emb2 = r2.json()["data"][0]["embedding"]
        assert emb1 == emb2

    def test_embedding_response_includes_usage(self):
        r = httpx.post(
            f"{EMBEDDING_URL}/v1/embeddings",
            json={"input": "usage check", "model": "bge-m3"},
            timeout=30,
        )
        data = r.json()
        assert "usage" in data
        assert data["usage"]["prompt_tokens"] > 0


# ---------------------------------------------------------------------------
# Profile isolation
# ---------------------------------------------------------------------------


class TestProfileIsolation:
    """Verify embedding service only starts with the embedding profile."""

    def test_default_profile_excludes_embedding(self):
        """'docker compose up' (no profile) should not list embedding."""
        result = subprocess.run(
            ["docker", "compose", "config", "--services"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        services = result.stdout.strip().splitlines()
        assert "embedding" not in services

    def test_embedding_profile_includes_embedding(self):
        result = subprocess.run(
            ["docker", "compose", "--profile", "embedding", "config", "--services"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        services = result.stdout.strip().splitlines()
        assert "embedding" in services

    def test_embedding_profile_includes_all_core_services(self):
        """The embedding profile should start core services too."""
        result = subprocess.run(
            ["docker", "compose", "--profile", "embedding", "config", "--services"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        services = set(result.stdout.strip().splitlines())
        assert {"db", "api", "web", "worker"}.issubset(services)
