from __future__ import annotations

from dataclasses import dataclass, field
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
