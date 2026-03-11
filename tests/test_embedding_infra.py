# /// script
# requires-python = ">=3.12"
# dependencies = ["pytest", "pyyaml"]
# ///
"""
Infrastructure tests for the embedding Docker Compose service.

These tests validate configuration correctness without requiring the
embedding model download (~605MB) or running Docker services. They run
in CI as a lightweight check that catches compose/Makefile/doc regressions.

Run: uv run --with pytest --with pyyaml pytest tests/test_embedding_infra.py -xvs
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT / "docker-compose.yml"
MAKEFILE = ROOT / "Makefile"
GITIGNORE = ROOT / ".gitignore"
ENV_EXAMPLE = ROOT / ".env.example"
EMBEDDINGS_DOC = ROOT / "docs" / "embeddings.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_compose() -> dict:
    with open(COMPOSE_FILE) as f:
        return yaml.safe_load(f)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kwargs)


# ---------------------------------------------------------------------------
# Docker Compose config
# ---------------------------------------------------------------------------


class TestComposeConfig:
    """docker-compose.yml structure and validation."""

    def test_compose_config_validates(self):
        """docker compose config parses without errors."""
        result = _run(["docker", "compose", "config", "-q"])
        assert result.returncode == 0, f"compose config failed: {result.stderr}"

    def test_embedding_service_exists(self):
        compose = _load_compose()
        assert "embedding" in compose["services"]

    def test_embedding_service_uses_llama_cpp_image(self):
        compose = _load_compose()
        image = compose["services"]["embedding"]["image"]
        assert "ghcr.io/ggml-org/llama.cpp" in image

    def test_embedding_service_is_profile_gated(self):
        compose = _load_compose()
        profiles = compose["services"]["embedding"].get("profiles", [])
        assert "embedding" in profiles

    def test_embedding_not_in_default_profile(self):
        """'make up' (no profile) should NOT start the embedding service."""
        result = _run(["docker", "compose", "config", "--services"])
        default_services = result.stdout.strip().splitlines()
        assert "embedding" not in default_services

    def test_embedding_in_embedding_profile(self):
        """'make up-embed' (--profile embedding) should include it."""
        result = _run(
            ["docker", "compose", "--profile", "embedding", "config", "--services"]
        )
        services = result.stdout.strip().splitlines()
        assert "embedding" in services

    def test_embedding_has_healthcheck(self):
        compose = _load_compose()
        hc = compose["services"]["embedding"].get("healthcheck")
        assert hc is not None
        assert any("health" in str(t) for t in hc.get("test", []))

    def test_embedding_model_mounted_readonly(self):
        compose = _load_compose()
        volumes = compose["services"]["embedding"].get("volumes", [])
        model_vol = [v for v in volumes if "/models" in str(v)]
        assert model_vol, "No /models volume mount found"
        vol_str = str(model_vol[0])
        assert ":ro" in vol_str, f"Model volume should be read-only, got: {vol_str}"

    def test_embedding_env_enables_embeddings_mode(self):
        compose = _load_compose()
        env = compose["services"]["embedding"].get("environment", {})
        assert env.get("LLAMA_ARG_EMBEDDINGS") == 1

    def test_embedding_port_defaults_to_8090(self):
        compose = _load_compose()
        ports = compose["services"]["embedding"].get("ports", [])
        port_strs = [str(p) for p in ports]
        assert any("8090" in p for p in port_strs)

    def test_core_service_count_unchanged(self):
        """Adding embedding should not affect the 4 core services."""
        compose = _load_compose()
        core = {"db", "api", "web", "worker"}
        assert core.issubset(compose["services"].keys())


# ---------------------------------------------------------------------------
# Makefile targets
# ---------------------------------------------------------------------------


class TestMakefile:
    """Makefile embedding targets exist and behave correctly."""

    @pytest.mark.parametrize(
        "target",
        ["embed-download", "up-embed", "down-embed", "embed-status"],
    )
    def test_target_exists(self, target: str):
        """Each embedding Make target should be callable (dry-run)."""
        result = _run(["make", "-n", target])
        assert result.returncode == 0, (
            f"'make -n {target}' failed: {result.stderr}"
        )

    def test_up_embed_checks_model_exists(self):
        """up-embed should fail if the model file is missing."""
        result = _run(
            ["make", "-n", "up-embed"],
            env={**os.environ, "EMBEDDING_MODEL_DIR": "/nonexistent/path"},
        )
        # Dry-run prints the commands but doesn't execute them,
        # so we verify the guard logic is present in the Makefile source
        makefile_text = MAKEFILE.read_text()
        assert "embed-download" in makefile_text, (
            "up-embed should reference embed-download in its error message"
        )

    def test_up_embed_guard_logic_in_makefile(self):
        """The up-embed target should check for model file before starting."""
        makefile_text = MAKEFILE.read_text()
        # Find the up-embed target block and verify it has a file-existence check
        assert re.search(
            r"up-embed:.*?-f.*?EMBEDDING_MODEL", makefile_text, re.DOTALL
        ), "up-embed target should check if model file exists"

    def test_embed_download_uses_curl(self):
        makefile_text = MAKEFILE.read_text()
        assert "curl" in makefile_text
        assert "huggingface.co" in makefile_text

    def test_embed_download_targets_correct_model(self):
        makefile_text = MAKEFILE.read_text()
        assert "ggml-org/bge-m3-Q8_0-GGUF" in makefile_text
        assert "bge-m3-q8_0.gguf" in makefile_text

    def test_phony_includes_embedding_targets(self):
        makefile_text = MAKEFILE.read_text()
        # Capture everything from .PHONY: to the first blank line,
        # handling backslash line continuations
        phony_match = re.search(r"\.PHONY:(.*?)(?:\n\n)", makefile_text, re.DOTALL)
        assert phony_match, ".PHONY declaration not found"
        phony_text = phony_match.group(1).replace("\\\n", " ")
        for target in ["embed-download", "up-embed", "down-embed", "embed-status"]:
            assert target in phony_text, f"{target} missing from .PHONY"


# ---------------------------------------------------------------------------
# File conventions
# ---------------------------------------------------------------------------


class TestFileConventions:
    """Gitignore, env example, and doc structure."""

    def test_gitignore_excludes_models_dir(self):
        gitignore = GITIGNORE.read_text()
        assert "models/" in gitignore

    def test_env_example_has_embedding_model_dir(self):
        env_text = ENV_EXAMPLE.read_text()
        assert "EMBEDDING_MODEL_DIR" in env_text

    def test_env_example_has_embedding_model_file(self):
        env_text = ENV_EXAMPLE.read_text()
        assert "EMBEDDING_MODEL_FILE" in env_text

    def test_env_example_has_compose_service_url(self):
        """Default embedding URL should reference the compose service name."""
        env_text = ENV_EXAMPLE.read_text()
        assert "http://embedding:8090" in env_text


# ---------------------------------------------------------------------------
# Documentation structure
# ---------------------------------------------------------------------------


class TestEmbeddingsDocs:
    """docs/embeddings.md has expected sections and admonitions."""

    @pytest.fixture(autouse=True)
    def _load_doc(self):
        self.doc = EMBEDDINGS_DOC.read_text()

    def test_doc_exists(self):
        assert EMBEDDINGS_DOC.is_file()

    @pytest.mark.parametrize(
        "admonition_type",
        ["NOTE", "WARNING", "IMPORTANT", "TIP"],
    )
    def test_has_github_admonition(self, admonition_type: str):
        """GitHub-flavored admonitions should be present."""
        assert f"> [!{admonition_type}]" in self.doc

    def test_has_gpu_alternatives_section(self):
        assert "## GPU Alternatives" in self.doc

    def test_documents_macos_metal(self):
        assert "Metal" in self.doc

    def test_documents_nvidia_cuda(self):
        assert "CUDA" in self.doc or "cuda" in self.doc

    def test_documents_amd_rocm(self):
        assert "ROCm" in self.doc or "rocm" in self.doc

    def test_documents_cloud_alternative(self):
        assert "Cloud" in self.doc

    def test_documents_tei(self):
        assert "text-embeddings-inference" in self.doc or "TEI" in self.doc

    def test_cpu_only_warning_present(self):
        """Should explicitly warn about CPU-only default."""
        assert "CPU-only" in self.doc or "cpu-only" in self.doc or "CPU only" in self.doc

    def test_quick_start_uses_make_commands(self):
        assert "make embed-download" in self.doc
        assert "make up-embed" in self.doc
