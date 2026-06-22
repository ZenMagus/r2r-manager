from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.r2r_client import R2RReadOnlyClient, R2RReadResult


@dataclass(frozen=True)
class R2RProbeReport:
    base_url: str
    reachable: bool
    auth_required: bool
    openapi_available: bool
    collections_supported: bool
    documents_supported: bool
    metadata_supported: bool
    archive_or_inactive_evidence: str
    delete_supported_evidence: str
    update_supported_evidence: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    openapi_paths: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "reachable": self.reachable,
            "auth_required": self.auth_required,
            "openapi_available": self.openapi_available,
            "collections_supported": self.collections_supported,
            "documents_supported": self.documents_supported,
            "metadata_supported": self.metadata_supported,
            "archive_or_inactive_evidence": self.archive_or_inactive_evidence,
            "delete_supported_evidence": self.delete_supported_evidence,
            "update_supported_evidence": self.update_supported_evidence,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "openapi_paths": list(self.openapi_paths),
        }


def probe_r2r(client: R2RReadOnlyClient | None = None) -> R2RProbeReport:
    client = client or R2RReadOnlyClient()
    health = client.get_health()
    openapi = client.get_openapi_schema()
    collections = client.list_collections()
    documents = client.list_documents()

    warnings: list[str] = []
    notes: list[str] = ["probe is read-only; no R2R mutation endpoints were called"]
    for label, result in {"health": health, "openapi": openapi, "collections": collections, "documents": documents}.items():
        if not result.ok:
            warnings.append(f"{label}:{result.status}")

    openapi_paths = _openapi_paths(openapi.data) if openapi.ok else ()
    method_evidence = _method_evidence(openapi.data) if openapi.ok else {}
    archive_evidence = _archive_evidence(openapi.data) if openapi.ok else "unknown_openapi_unavailable"

    auth_required = any(result.status == "auth_required" for result in (health, openapi, collections, documents))
    reachable = health.ok or openapi.ok or collections.status == "auth_required" or documents.status == "auth_required"

    return R2RProbeReport(
        base_url=client.config.base_url,
        reachable=reachable,
        auth_required=auth_required,
        openapi_available=openapi.ok,
        collections_supported=collections.ok or _has_get_path(openapi_paths, "/v3/collections"),
        documents_supported=documents.ok or _has_get_path(openapi_paths, "/v3/documents"),
        metadata_supported=_metadata_supported(openapi.data) if openapi.ok else False,
        archive_or_inactive_evidence=archive_evidence,
        delete_supported_evidence=method_evidence.get("delete", "unknown_openapi_unavailable"),
        update_supported_evidence=method_evidence.get("update", "unknown_openapi_unavailable"),
        notes=tuple(notes),
        warnings=tuple(dict.fromkeys(warnings)),
        openapi_paths=openapi_paths,
    )


def _openapi_paths(data: Any) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ()
    paths = data.get("paths")
    if not isinstance(paths, dict):
        return ()
    return tuple(sorted(str(path) for path in paths))


def _method_evidence(data: Any) -> dict[str, str]:
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        return {"delete": "unknown_openapi_unavailable", "update": "unknown_openapi_unavailable"}
    delete_paths: list[str] = []
    update_paths: list[str] = []
    for path, methods in data["paths"].items():
        if not isinstance(methods, dict):
            continue
        lowered = {str(method).lower() for method in methods}
        if "delete" in lowered:
            delete_paths.append(str(path))
        if lowered & {"put", "patch"}:
            update_paths.append(str(path))
    return {
        "delete": "present:" + ",".join(sorted(delete_paths)) if delete_paths else "not_evidenced",
        "update": "present:" + ",".join(sorted(update_paths)) if update_paths else "not_evidenced",
    }


def _archive_evidence(data: Any) -> str:
    text = repr(data).lower()
    matches = [word for word in ("archive", "inactive", "stale", "version") if word in text]
    return "present:" + ",".join(matches) if matches else "not_evidenced"


def _metadata_supported(data: Any) -> bool:
    return "metadata" in repr(data).lower()


def _has_get_path(paths: tuple[str, ...], path: str) -> bool:
    return path in paths
