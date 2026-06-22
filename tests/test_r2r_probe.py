from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.r2r_client import R2RReadOnlyClient
from app.r2r_config import DEFAULT_R2R_BASE_URL, DEFAULT_R2R_WRITE_TIMEOUT_SECONDS, get_r2r_config
from app.r2r_probe import probe_r2r


ROOT = Path(__file__).resolve().parents[1]


class FakeHttpClient:
    def __init__(self, responses: dict[str, httpx.Response] | None = None, exc: Exception | None = None) -> None:
        self.responses = responses or {}
        self.exc = exc
        self.calls: list[str] = []

    def get(self, endpoint: str, *, headers: dict[str, str]):
        self.calls.append(endpoint)
        if self.exc:
            raise self.exc
        return self.responses[endpoint]


def test_r2r_config_defaults_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("R2R_BASE_URL", raising=False)
    monkeypatch.delenv("R2R_API_KEY", raising=False)
    monkeypatch.delenv("R2R_TOKEN", raising=False)
    monkeypatch.delenv("R2R_WRITE_TIMEOUT_SECONDS", raising=False)

    assert get_r2r_config().base_url == DEFAULT_R2R_BASE_URL
    assert get_r2r_config().write_timeout_seconds == DEFAULT_R2R_WRITE_TIMEOUT_SECONDS

    monkeypatch.setenv("R2R_BASE_URL", "http://r2r.test:7272/")
    monkeypatch.setenv("R2R_API_KEY", "secret")
    monkeypatch.setenv("R2R_WRITE_TIMEOUT_SECONDS", "450")

    config = get_r2r_config()
    assert config.base_url == "http://r2r.test:7272"
    assert config.api_key == "secret"
    assert config.write_timeout_seconds == 450.0


def test_r2r_client_handles_reachable_health_response() -> None:
    fake = FakeHttpClient({"http://r2r.test/v3/health": _response("http://r2r.test/v3/health", {"results": {"message": "ok"}})})

    result = R2RReadOnlyClient(config=_config(), client=fake).get_health()

    assert result.ok is True
    assert result.data["results"]["message"] == "ok"


def test_r2r_client_handles_unreachable_service_cleanly() -> None:
    fake = FakeHttpClient(exc=httpx.ConnectError("connection refused"))

    result = R2RReadOnlyClient(config=_config(), client=fake).get_health()

    assert result.ok is False
    assert result.status == "unreachable"


def test_openapi_available_response_is_parsed() -> None:
    fake = FakeHttpClient(
        {
            "http://r2r.test/v3/health": _response("http://r2r.test/v3/health", {"results": {"message": "ok"}}),
            "http://r2r.test/openapi.json": _response("http://r2r.test/openapi.json", _openapi()),
            "http://r2r.test/v3/collections?limit=10&offset=0": _response("http://r2r.test/v3/collections?limit=10&offset=0", {"results": []}),
            "http://r2r.test/v3/documents?limit=10&offset=0": _response("http://r2r.test/v3/documents?limit=10&offset=0", {"results": []}),
        }
    )

    report = probe_r2r(R2RReadOnlyClient(config=_config(), client=fake))

    assert report.reachable is True
    assert report.openapi_available is True
    assert report.collections_supported is True
    assert report.documents_supported is True
    assert report.metadata_supported is True
    assert report.delete_supported_evidence.startswith("present:")
    assert report.update_supported_evidence.startswith("present:")
    assert report.archive_or_inactive_evidence.startswith("present:")


def test_missing_openapi_and_unsupported_lists_are_reported_cleanly() -> None:
    fake = FakeHttpClient(
        {
            "http://r2r.test/v3/health": _response("http://r2r.test/v3/health", {"results": {"message": "ok"}}),
            "http://r2r.test/openapi.json": _response("http://r2r.test/openapi.json", {"detail": "missing"}, status_code=404),
            "http://r2r.test/openapi_spec": _response("http://r2r.test/openapi_spec", {"detail": "missing"}, status_code=404),
            "http://r2r.test/v3/collections?limit=10&offset=0": _response("http://r2r.test/v3/collections?limit=10&offset=0", {"detail": "missing"}, status_code=404),
            "http://r2r.test/v3/documents?limit=10&offset=0": _response("http://r2r.test/v3/documents?limit=10&offset=0", {"detail": "missing"}, status_code=404),
        }
    )

    report = probe_r2r(R2RReadOnlyClient(config=_config(), client=fake))

    assert report.reachable is True
    assert report.openapi_available is False
    assert report.collections_supported is False
    assert report.documents_supported is False
    assert "openapi:unsupported" in report.warnings


def test_auth_required_is_reported() -> None:
    fake = FakeHttpClient(
        {
            "http://r2r.test/v3/health": _response("http://r2r.test/v3/health", {"detail": "auth"}, status_code=401),
            "http://r2r.test/openapi.json": _response("http://r2r.test/openapi.json", {"detail": "auth"}, status_code=401),
            "http://r2r.test/openapi_spec": _response("http://r2r.test/openapi_spec", {"detail": "auth"}, status_code=401),
            "http://r2r.test/v3/collections?limit=10&offset=0": _response("http://r2r.test/v3/collections?limit=10&offset=0", {"detail": "auth"}, status_code=401),
            "http://r2r.test/v3/documents?limit=10&offset=0": _response("http://r2r.test/v3/documents?limit=10&offset=0", {"detail": "auth"}, status_code=401),
        }
    )

    report = probe_r2r(R2RReadOnlyClient(config=_config(), client=fake))

    assert report.auth_required is True
    assert report.reachable is True


def test_check_r2r_state_json_runs_with_unreachable_service() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_r2r_state.py", "--base-url", "http://127.0.0.1:1", "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reachable"] is False
    assert payload["base_url"] == "http://127.0.0.1:1"


def _response(endpoint: str, data: dict, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", endpoint), json=data)


def _config():
    from app.r2r_config import R2RConfig

    return R2RConfig(base_url="http://r2r.test", timeout_seconds=1.0)


def _openapi() -> dict:
    return {
        "paths": {
            "/v3/health": {"get": {}},
            "/v3/collections": {"get": {}, "post": {}},
            "/v3/collections/{id}": {"get": {}, "delete": {}},
            "/v3/documents": {"get": {}, "post": {}},
            "/v3/documents/{id}": {"get": {}, "patch": {}, "delete": {}},
        },
        "components": {
            "schemas": {
                "Document": {
                    "properties": {
                        "id": {"type": "string"},
                        "metadata": {"type": "object"},
                        "version": {"type": "string"},
                        "is_archived": {"type": "boolean"},
                    }
                }
            }
        },
    }
