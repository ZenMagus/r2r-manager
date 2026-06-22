from __future__ import annotations

from dataclasses import dataclass, field
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.r2r_config import R2RConfig, get_r2r_config


@dataclass(frozen=True)
class R2RReadResult:
    ok: bool
    status: str
    endpoint: str
    http_status_code: int | None = None
    data: Any | None = None
    message: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class R2RWriteResult:
    ok: bool
    status: str
    endpoint: str
    http_status_code: int | None = None
    data: Any | None = None
    message: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    attempted: bool = False
    remote_state: str = "not_changed"


class R2RReadOnlyClient:
    def __init__(self, config: R2RConfig | None = None, *, client: Any | None = None) -> None:
        self.config = config or get_r2r_config()
        self._client = client

    def get_health(self) -> R2RReadResult:
        return self._get("/v3/health")

    def get_openapi_schema(self) -> R2RReadResult:
        first = self._get("/openapi.json")
        if first.ok:
            return first
        second = self._get("/openapi_spec")
        if second.ok:
            return second
        return R2RReadResult(
            ok=False,
            status="unsupported",
            endpoint="/openapi.json,/openapi_spec",
            http_status_code=second.http_status_code or first.http_status_code,
            message="OpenAPI schema was not available from known read-only endpoints.",
            warnings=tuple(dict.fromkeys([*first.warnings, *second.warnings])),
        )

    def list_collections(self, *, limit: int = 10, offset: int = 0) -> R2RReadResult:
        return self._get(f"/v3/collections?limit={limit}&offset={offset}")

    def list_all_collections(self, *, page_size: int = 100) -> R2RReadResult:
        items: list[Any] = []
        offset = 0
        last_status_code: int | None = None
        while True:
            result = self.list_collections(limit=page_size, offset=offset)
            last_status_code = result.http_status_code
            if not result.ok:
                return result
            page_items = _extract_items(result.data)
            items.extend(page_items)
            total = _extract_total(result.data)
            if total is not None and len(items) >= total:
                break
            if len(page_items) < page_size:
                break
            offset += page_size
        return R2RReadResult(True, "ok", f"/v3/collections?limit={page_size}&offset=*", http_status_code=last_status_code, data={"results": items})

    def list_documents(self, *, limit: int = 10, offset: int = 0, collection_id: str | None = None) -> R2RReadResult:
        suffix = f"limit={limit}&offset={offset}"
        if collection_id:
            suffix = f"{suffix}&collection_id={collection_id}"
        return self._get(f"/v3/documents?{suffix}")

    def list_all_documents(self, *, page_size: int = 100) -> R2RReadResult:
        items: list[Any] = []
        offset = 0
        last_status_code: int | None = None
        while True:
            result = self.list_documents(limit=page_size, offset=offset)
            last_status_code = result.http_status_code
            if not result.ok:
                return result
            page_items = _extract_items(result.data)
            items.extend(page_items)
            total = _extract_total(result.data)
            if total is not None and len(items) >= total:
                break
            if len(page_items) < page_size:
                break
            offset += page_size
        return R2RReadResult(True, "ok", f"/v3/documents?limit={page_size}&offset=*", http_status_code=last_status_code, data={"results": items})

    def _get(self, path: str) -> R2RReadResult:
        endpoint = f"{self.config.base_url}{path}"
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        try:
            response = self._request_get(endpoint, headers=headers)
        except httpx.TimeoutException as exc:
            return R2RReadResult(False, "timeout", path, message="R2R request timed out.", warnings=(type(exc).__name__,))
        except httpx.HTTPError as exc:
            return R2RReadResult(False, "unreachable", path, message="R2R is unreachable.", warnings=(type(exc).__name__, str(exc)))

        status_code = getattr(response, "status_code", None)
        if status_code in {401, 403}:
            return R2RReadResult(False, "auth_required", path, http_status_code=status_code, message=f"R2R returned HTTP {status_code}.")
        if status_code is not None and status_code == 404:
            return R2RReadResult(False, "unsupported", path, http_status_code=status_code, message="R2R endpoint was not found.")
        if status_code is not None and status_code >= 400:
            return R2RReadResult(False, "http_error", path, http_status_code=status_code, message=f"R2R returned HTTP {status_code}.")
        try:
            data = response.json()
        except ValueError:
            data = getattr(response, "text", None)
        return R2RReadResult(True, "ok", path, http_status_code=status_code, data=data)

    def _request_get(self, endpoint: str, *, headers: dict[str, str]):
        if self._client is not None:
            return self._client.get(endpoint, headers=headers)
        with httpx.Client(timeout=httpx.Timeout(self.config.timeout_seconds)) as client:
            return client.get(endpoint, headers=headers)


class R2RWriteClient(R2RReadOnlyClient):
    """Small write-capable R2R client.

    Keep write methods explicit and narrow. There are intentionally no delete,
    archive, or collection-create helpers in this slice.
    """

    def create_document_from_file(
        self,
        file_path: Path,
        *,
        metadata: dict[str, Any],
        collection_ids: list[str] | None = None,
    ) -> R2RWriteResult:
        path = Path(file_path)
        if not path.is_file():
            return R2RWriteResult(False, "local_file_missing", "/v3/documents", message="Local source file is missing.")

        data: dict[str, str] = {
            "metadata": json.dumps(metadata, sort_keys=True),
            "run_with_orchestration": "false",
        }
        if collection_ids:
            data["collection_ids"] = json.dumps(collection_ids)
        upload_name, content_type = _upload_name_and_content_type(path)
        endpoint = f"{self.config.base_url}/v3/documents"
        headers = self._auth_headers()
        try:
            with path.open("rb") as handle:
                files = {"file": (upload_name, handle, content_type)}
                response = self._request_post(endpoint, headers=headers, data=data, files=files)
        except httpx.TimeoutException as exc:
            return R2RWriteResult(False, "timeout", "/v3/documents", message="R2R document create timed out; remote state is unknown until a read-only comparison is run.", warnings=(type(exc).__name__,), attempted=True, remote_state="unknown")
        except httpx.HTTPError as exc:
            return R2RWriteResult(False, "unreachable", "/v3/documents", message="R2R write failed; remote state is unknown until a read-only comparison is run.", warnings=(type(exc).__name__, str(exc)), attempted=True, remote_state="unknown")
        except OSError as exc:
            return R2RWriteResult(False, "local_file_error", "/v3/documents", message="Local source file could not be read.", warnings=(type(exc).__name__,))
        return self._write_result_from_response(response, "/v3/documents")

    def replace_document_metadata(self, document_id: str, metadata: dict[str, Any]) -> R2RWriteResult:
        endpoint = f"{self.config.base_url}/v3/documents/{document_id}/metadata"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        try:
            response = self._request_put(endpoint, headers=headers, content=json.dumps([metadata], sort_keys=True))
        except httpx.TimeoutException as exc:
            return R2RWriteResult(False, "timeout", f"/v3/documents/{document_id}/metadata", message="R2R metadata replace timed out; remote state is unknown until a read-only comparison is run.", warnings=(type(exc).__name__,), attempted=True, remote_state="unknown")
        except httpx.HTTPError as exc:
            return R2RWriteResult(False, "unreachable", f"/v3/documents/{document_id}/metadata", message="R2R write failed; remote state is unknown until a read-only comparison is run.", warnings=(type(exc).__name__, str(exc)), attempted=True, remote_state="unknown")
        return self._write_result_from_response(response, f"/v3/documents/{document_id}/metadata")

    def _auth_headers(self) -> dict[str, str]:
        if not self.config.api_key:
            return {}
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _request_post(self, endpoint: str, *, headers: dict[str, str], data: dict[str, str], files: dict[str, Any]):
        if self._client is not None:
            return self._client.post(endpoint, headers=headers, data=data, files=files)
        with httpx.Client(timeout=httpx.Timeout(self.config.write_timeout_seconds)) as client:
            return client.post(endpoint, headers=headers, data=data, files=files)

    def _request_put(self, endpoint: str, *, headers: dict[str, str], content: str):
        if self._client is not None:
            return self._client.put(endpoint, headers=headers, content=content)
        with httpx.Client(timeout=httpx.Timeout(self.config.write_timeout_seconds)) as client:
            return client.put(endpoint, headers=headers, content=content)

    def _write_result_from_response(self, response: Any, endpoint: str) -> R2RWriteResult:
        status_code = getattr(response, "status_code", None)
        if status_code in {401, 403}:
            return R2RWriteResult(False, "auth_required", endpoint, http_status_code=status_code, message=f"R2R returned HTTP {status_code}.", attempted=True, remote_state="unknown")
        if status_code is not None and status_code == 404:
            return R2RWriteResult(False, "unsupported", endpoint, http_status_code=status_code, message="R2R endpoint was not found.", attempted=True, remote_state="unknown")
        if status_code is not None and status_code >= 400:
            return R2RWriteResult(False, "http_error", endpoint, http_status_code=status_code, message=f"R2R returned HTTP {status_code}.", attempted=True, remote_state="unknown")
        try:
            data = response.json()
        except ValueError:
            data = getattr(response, "text", None)
        return R2RWriteResult(True, "ok", endpoint, http_status_code=status_code, data=data, attempted=True, remote_state="confirmed")


def _upload_name_and_content_type(path: Path) -> tuple[str, str]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return f"{path.name}.txt", "text/plain"
    return path.name, mimetypes.guess_type(path.name)[0] or "text/markdown"


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    current: Any = payload
    for key in ("results", "data"):
        if isinstance(current, dict) and key in current:
            current = current[key]
    if isinstance(current, list):
        return current
    if isinstance(current, dict):
        for key in ("results", "items", "documents"):
            value = current.get(key)
            if isinstance(value, list):
                return value
    return []


def _extract_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    candidates = [payload]
    if isinstance(payload.get("results"), dict):
        candidates.append(payload["results"])
    if isinstance(payload.get("data"), dict):
        candidates.append(payload["data"])
    for candidate in candidates:
        for key in ("total_entries", "total", "count"):
            value = candidate.get(key)
            if isinstance(value, int):
                return value
    return None
