"""Tests for configuration integrity — catches high-severity config issues
found during documentation audits.

These tests verify:
1. FRONTEND_URL is defined and used dynamically in Slack link generation
2. RECOMMENDATION_MODEL is defined with the expected default in worker config
3. All API routes are documented in docs/api-reference.md
"""
import ast
import re
from pathlib import Path
from unittest.mock import patch

import pytest


# Repo root resolution: works both locally and in Docker.
# Locally: backend/tests/test_config_integrity.py -> ../../ = repo root
# In Docker: /app/tests/test_config_integrity.py -> /app/.. but worker/ isn't mounted.
# We check multiple candidate paths for cross-container file access.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT_CANDIDATES = [
    _BACKEND_DIR.parent,                 # local dev: backend/../
    Path("/repo"),                        # optional Docker mount
]


def _repo_root() -> Path | None:
    """Find the repo root directory containing worker/ and docs/.

    Returns None when running inside Docker where only /app (backend) is mounted
    and the repo root is not accessible.
    """
    for candidate in _REPO_ROOT_CANDIDATES:
        if (candidate / "docker-compose.yml").exists():
            return candidate
    return None


def _require_repo_root() -> Path:
    """Return repo root or skip the test if running in Docker."""
    root = _repo_root()
    if root is None:
        pytest.skip("Repo root not accessible (running inside Docker container)")
    return root


# ---------------------------------------------------------------------------
# 1. FRONTEND_URL must be accessible to the API service
# ---------------------------------------------------------------------------

class TestFrontendUrlConfig:
    """Verify FRONTEND_URL is defined in backend settings and used by the
    Slack service to build links (not hardcoded)."""

    def test_frontend_url_setting_exists(self):
        """The Settings class must declare FRONTEND_URL with a sensible default."""
        from app.config import Settings

        assert "FRONTEND_URL" in Settings.model_fields, (
            "FRONTEND_URL is not declared in Settings — "
            "Slack notifications need it to build links"
        )
        # Default should be a valid URL (not empty)
        default_val = Settings.model_fields["FRONTEND_URL"].default
        assert default_val, "FRONTEND_URL default must not be empty"
        assert default_val.startswith("http"), (
            f"FRONTEND_URL default '{default_val}' does not look like a URL"
        )

    def test_frontend_url_default_is_localhost(self):
        """Default value should point to the local dev frontend."""
        from app.config import Settings

        default = Settings.model_fields["FRONTEND_URL"].default
        assert "localhost" in default or "127.0.0.1" in default, (
            f"Expected FRONTEND_URL default to target localhost for dev, got '{default}'"
        )

    def test_question_link_uses_frontend_url_setting(self):
        """_question_link must use settings.FRONTEND_URL, not a hardcoded URL."""
        from app.services.slack import _question_link
        from app.services import slack

        custom_url = "https://my-custom-domain.example.com"
        with patch.object(slack.settings, "FRONTEND_URL", custom_url):
            link = _question_link("q-abc-123", "View")
        assert custom_url in link, (
            f"_question_link did not use settings.FRONTEND_URL — "
            f"expected '{custom_url}' in link, got: {link}"
        )
        assert "q-abc-123" in link, "Question ID missing from generated link"

    def test_answer_link_uses_frontend_url_setting(self):
        """_answer_link must use settings.FRONTEND_URL, not a hardcoded URL."""
        from app.services.slack import _answer_link
        from app.services import slack

        custom_url = "https://prod.example.com"
        with patch.object(slack.settings, "FRONTEND_URL", custom_url):
            link = _answer_link("a-xyz-789", "View")
        assert custom_url in link, (
            f"_answer_link did not use settings.FRONTEND_URL — "
            f"expected '{custom_url}' in link, got: {link}"
        )
        assert "a-xyz-789" in link, "Answer ID missing from generated link"

    def test_question_link_format_is_slack_compatible(self):
        """Links must use Slack's <url|text> format."""
        from app.services.slack import _question_link
        from app.services import slack

        with patch.object(slack.settings, "FRONTEND_URL", "http://example.com"):
            link = _question_link("q-1", "Click here")
        assert link.startswith("<"), "Slack link must start with '<'"
        assert link.endswith(">"), "Slack link must end with '>'"
        assert "|Click here>" in link, "Slack link must contain |text>"

    def test_answer_link_format_is_slack_compatible(self):
        """Links must use Slack's <url|text> format."""
        from app.services.slack import _answer_link
        from app.services import slack

        with patch.object(slack.settings, "FRONTEND_URL", "http://example.com"):
            link = _answer_link("a-1", "View answer")
        assert link.startswith("<"), "Slack link must start with '<'"
        assert link.endswith(">"), "Slack link must end with '>'"
        assert "|View answer>" in link, "Slack link must contain |text>"


# ---------------------------------------------------------------------------
# 2. RECOMMENDATION_MODEL must be accessible to the worker service
#
# The worker runs in a separate container, so we cannot import its code
# directly. Instead we parse the config file with AST to extract the
# field definition and default value.
# ---------------------------------------------------------------------------

def _parse_worker_settings_defaults() -> dict[str, str]:
    """Parse worker/worker/config.py using AST to extract WorkerSettings
    field names and their default string values.

    Returns a dict like {"RECOMMENDATION_MODEL": "anthropic/claude-haiku-4-5-20251001"}.
    """
    root = _require_repo_root()
    config_path = root / "worker" / "worker" / "config.py"
    assert config_path.exists(), (
        f"Worker config not found at {config_path} — "
        "has the file moved?"
    )
    tree = ast.parse(config_path.read_text())

    defaults: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "WorkerSettings":
            for item in node.body:
                # Annotated assignments: FIELD: type = "default"
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    if item.value is not None and isinstance(item.value, ast.Constant):
                        defaults[field_name] = item.value.value
    return defaults


class TestRecommendationModelConfig:
    """Verify RECOMMENDATION_MODEL is defined in worker settings with the
    expected default.

    Uses AST parsing of worker/worker/config.py because the worker runs
    in a separate container and cannot be imported from the backend test suite.
    """

    def test_worker_config_file_exists(self):
        """The worker config file must exist at the expected location."""
        root = _require_repo_root()
        config_path = root / "worker" / "worker" / "config.py"
        assert config_path.exists(), (
            f"Worker config not found at {config_path}"
        )

    def test_recommendation_model_setting_exists(self):
        """The WorkerSettings class must declare RECOMMENDATION_MODEL."""
        defaults = _parse_worker_settings_defaults()
        assert "RECOMMENDATION_MODEL" in defaults, (
            "RECOMMENDATION_MODEL is not declared in WorkerSettings — "
            "respondent recommendation requires it"
        )

    def test_recommendation_model_default_value(self):
        """Default should be the expected Haiku model."""
        defaults = _parse_worker_settings_defaults()
        default = defaults.get("RECOMMENDATION_MODEL")
        assert default == "anthropic/claude-haiku-4-5-20251001", (
            f"Expected RECOMMENDATION_MODEL default to be "
            f"'anthropic/claude-haiku-4-5-20251001', got '{default}'"
        )

    def test_recommendation_model_is_not_empty_by_default(self):
        """Unlike optional settings (EMBEDDING_MODEL), RECOMMENDATION_MODEL
        should have a usable default so recommendation works out of the box."""
        defaults = _parse_worker_settings_defaults()
        default = defaults.get("RECOMMENDATION_MODEL", "")
        assert default, "RECOMMENDATION_MODEL default must not be empty"

    def test_recommendation_model_in_docker_compose(self):
        """docker-compose.yml must pass RECOMMENDATION_MODEL to the worker service."""
        root = _require_repo_root()
        compose_path = root / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found at repo root"
        compose_text = compose_path.read_text()
        assert "RECOMMENDATION_MODEL" in compose_text, (
            "RECOMMENDATION_MODEL is not passed to the worker service in "
            "docker-compose.yml — the worker will use its hardcoded default "
            "and ignore the host environment variable"
        )


# ---------------------------------------------------------------------------
# 3. All API routes must be documented
# ---------------------------------------------------------------------------

# Routes that are excluded from documentation checks (framework-generated
# or trivially obvious).
_EXCLUDED_PATHS = {
    "/health",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
}


class TestApiDocumentation:
    """Meta-test: verify that every registered API route appears in the
    API reference documentation. Catches documentation drift when new
    endpoints are added without updating the docs."""

    def _get_all_route_paths(self) -> list[str]:
        """Collect all route paths from the FastAPI app."""
        from app.main import app
        from fastapi.routing import APIRoute

        paths = []
        for route in app.routes:
            if isinstance(route, APIRoute):
                if route.path not in _EXCLUDED_PATHS:
                    paths.append(route.path)
        return sorted(set(paths))

    def _read_api_reference(self) -> str:
        """Read the API reference markdown file."""
        root = _require_repo_root()
        doc_path = root / "docs" / "api-reference.md"
        assert doc_path.exists(), (
            f"API reference doc not found at {doc_path} — "
            "create docs/api-reference.md or update the test path"
        )
        return doc_path.read_text()

    def _path_is_documented(self, path: str, doc_text: str) -> bool:
        """Check if a route path appears in the documentation in any
        recognizable form."""
        # 1. Exact match of the full path
        if path in doc_text:
            return True

        # 2. Without /api/v1 prefix (docs may use shorter form)
        short_path = path.replace("/api/v1/", "/")
        if short_path in doc_text:
            return True

        # 3. With generic parameter names: {question_id} -> {id}
        generic_path = re.sub(r"\{[^}]+\}", "{id}", path)
        if generic_path in doc_text:
            return True
        generic_short = re.sub(r"\{[^}]+\}", "{id}", short_path)
        if generic_short in doc_text:
            return True

        # 4. Check the path suffix (last two non-param segments)
        # e.g., for /api/v1/questions/{id}/submit -> "questions/{id}/submit"
        segments = [s for s in path.split("/") if s and s != "api" and s != "v1"]
        if len(segments) >= 2:
            suffix = "/".join(segments[-2:])
            if suffix in doc_text:
                return True
            # Also try with generic params
            generic_suffix = re.sub(r"\{[^}]+\}", "{id}", suffix)
            if generic_suffix in doc_text:
                return True

        # 5. For resource collection routes like /api/v1/questions,
        #    check if the resource name appears as a documented section
        non_param_segments = [s for s in segments if not s.startswith("{")]
        if non_param_segments:
            # Match patterns like "`/questions`" or "/questions" or "questions"
            resource = "/".join(non_param_segments)
            if resource in doc_text:
                return True

        return False

    def test_api_reference_doc_exists(self):
        """The API reference document must exist."""
        doc_text = self._read_api_reference()
        assert len(doc_text) > 100, "API reference doc is suspiciously short"

    def test_all_routes_are_documented(self):
        """Every non-trivial API route path must appear somewhere in the
        API reference documentation.

        This catches the case where a developer adds a new endpoint but
        forgets to document it."""
        doc_text = self._read_api_reference()
        route_paths = self._get_all_route_paths()

        assert len(route_paths) > 0, "No routes found — is the app configured correctly?"

        undocumented = []
        for path in route_paths:
            if not self._path_is_documented(path, doc_text):
                undocumented.append(path)

        if undocumented:
            msg_lines = [
                f"Found {len(undocumented)} undocumented API route(s) in docs/api-reference.md:",
            ]
            for p in undocumented:
                msg_lines.append(f"  - {p}")
            msg_lines.append(
                "\nAdd documentation for these endpoints or update "
                "_EXCLUDED_PATHS in the test if they should be excluded."
            )
            pytest.fail("\n".join(msg_lines))

    def test_route_count_sanity_check(self):
        """Guard against the app losing routes (e.g., a missing router include).

        If the route count drops below a reasonable minimum, something is wrong
        with app initialization."""
        route_paths = self._get_all_route_paths()
        # The app currently has ~30+ routes; fail if we drop below 15
        assert len(route_paths) >= 15, (
            f"Only {len(route_paths)} routes registered — expected at least 15. "
            "Check that all routers are included in api/v1/router.py."
        )
