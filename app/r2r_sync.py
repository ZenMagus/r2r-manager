from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.document_discovery import DocumentCandidate
from app.r2r_client import R2RReadOnlyClient, R2RWriteClient
from app.r2r_compare import ComparisonItem, R2RComparisonReport
from app.sync_plan import SyncPlan


SCHEMA_VERSION = "r2r-manager.docs.v1"
CREATE_ACTION = "would_create"
UPDATE_ACTION = "would_update"
MUTABLE_ACTIONS = {CREATE_ACTION, UPDATE_ACTION}


@dataclass(frozen=True)
class CollectionRef:
    collection_id: str
    name: str


@dataclass(frozen=True)
class SyncOperationResult:
    action: str
    project_id: str | None
    collection: str | None
    source_path: str | None
    status: str
    r2r_write: str
    remote_state: str = "not_changed"
    remote_document_id: str | None = None
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "project_id": self.project_id,
            "collection": self.collection,
            "source_path": self.source_path,
            "status": self.status,
            "r2r_write": self.r2r_write,
            "remote_state": self.remote_state,
            "remote_document_id": self.remote_document_id,
            "reason": self.reason,
            "error": self.error,
        }


@dataclass(frozen=True)
class R2RSyncReport:
    mode: str
    r2r_write: str
    remote_state: str
    operations: tuple[SyncOperationResult, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, Any]:
        by_status = Counter(item.status for item in self.operations)
        by_action = Counter(item.action for item in self.operations)
        by_project: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for item in self.operations:
            by_project[item.project_id or "unknown"][item.status] += 1
        return {
            "total": len(self.operations),
            "write_attempted": sum(item.r2r_write in {"attempted", "performed"} for item in self.operations),
            "created": by_status.get("created", 0),
            "updated": by_status.get("updated", 0),
            "skipped": sum(count for status, count in by_status.items() if status.startswith("skipped")),
            "stale_remote_report_only": by_action.get("stale_remote", 0),
            "errors": by_status.get("error", 0),
            "by_status": dict(sorted(by_status.items())),
            "by_action": dict(sorted(by_action.items())),
            "by_project": {project: dict(sorted(statuses.items())) for project, statuses in sorted(by_project.items())},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "r2r_write": self.r2r_write,
            "remote_state": self.remote_state,
            "summary": self.summary(),
            "operations": [item.to_dict() for item in self.operations],
            "warnings": list(self.warnings),
        }


def build_ingest_metadata(candidate: DocumentCandidate, *, sync_mode: str) -> dict[str, Any]:
    git = candidate.git
    return {
        "project_id": candidate.project_id,
        "collection": candidate.collection,
        "source_path": candidate.source_path,
        "content_sha256": candidate.content_sha256,
        "git_root": None if git is None else git.git_root,
        "git_branch": None if git is None else git.branch,
        "git_commit": None if git is None else git.commit,
        "git_dirty": None if git is None else git.dirty,
        "source_mtime": candidate.modified_at,
        "source_modified_time": candidate.modified_at,
        "source_size_bytes": candidate.size_bytes,
        "r2r_manager_version": SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
        "ingest_tool": "r2r-manager",
        "ingest_mode": sync_mode,
        "sync_mode": sync_mode,
    }


def build_sync_report(
    plan: SyncPlan,
    comparison: R2RComparisonReport,
    *,
    client: R2RReadOnlyClient | R2RWriteClient,
    apply: bool,
) -> R2RSyncReport:
    mode = "apply" if apply else "dry_run"
    candidate_by_key = {
        (candidate.project_id, candidate.collection, candidate.source_path): candidate
        for candidate in plan.candidates
        if candidate.exists and candidate.action != "skipped"
    }
    warnings: list[str] = list(comparison.warnings)
    collection_refs = resolve_collections(client)
    if collection_refs is None:
        warnings.append("collections_unavailable")
        collection_refs = {}

    operations: list[SyncOperationResult] = []
    for item in comparison.items:
        candidate = candidate_by_key.get((item.project_id, item.collection, item.source_path))
        if item.action == CREATE_ACTION:
            operations.append(_handle_create(item, candidate, collection_refs, client, apply=apply, sync_mode=mode))
        elif item.action == UPDATE_ACTION:
            operations.append(_handle_update(item, candidate, apply=apply))
        else:
            operations.append(
                SyncOperationResult(
                    action=item.action,
                    project_id=item.project_id,
                    collection=item.collection,
                    source_path=item.source_path,
                    status=_skip_status_for_action(item.action),
                    r2r_write="not_performed",
                    remote_document_id=item.remote_document_id,
                    reason=item.reason or "action is not eligible for create/update sync",
                )
            )

    if any(operation.r2r_write == "performed" for operation in operations):
        r2r_write = "performed"
    elif any(operation.r2r_write == "attempted" for operation in operations):
        r2r_write = "attempted"
    else:
        r2r_write = "not_performed"
    if any(operation.remote_state == "unknown" for operation in operations):
        remote_state = "unknown"
    elif r2r_write == "performed":
        remote_state = "confirmed"
    else:
        remote_state = "not_changed"
    return R2RSyncReport(
        mode=mode,
        r2r_write=r2r_write,
        remote_state=remote_state,
        operations=tuple(operations),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def resolve_collections(client: R2RReadOnlyClient) -> dict[str, CollectionRef] | None:
    result = client.list_all_collections()
    if not result.ok:
        return None
    refs: dict[str, CollectionRef] = {}
    for payload in _extract_collection_items(result.data):
        ref = normalize_collection(payload)
        if ref is not None:
            refs[ref.name] = ref
    return refs


def normalize_collection(payload: Any) -> CollectionRef | None:
    if not isinstance(payload, dict):
        return None
    collection_id = _first_str(payload, ("id", "collection_id"))
    name = _first_str(payload, ("name", "collection_name"))
    if collection_id is None or name is None:
        return None
    return CollectionRef(collection_id=collection_id, name=name)


def _handle_create(
    item: ComparisonItem,
    candidate: DocumentCandidate | None,
    collection_refs: dict[str, CollectionRef],
    client: R2RReadOnlyClient | R2RWriteClient,
    *,
    apply: bool,
    sync_mode: str,
) -> SyncOperationResult:
    if candidate is None:
        return _skipped(item, "candidate_missing")
    if item.collection not in collection_refs:
        return _skipped(item, "missing_collection")
    metadata = build_ingest_metadata(candidate, sync_mode=sync_mode)
    if not apply:
        return SyncOperationResult(item.action, item.project_id, item.collection, item.source_path, "dry_run", "not_performed", reason="would create document")
    if not isinstance(client, R2RWriteClient):
        return _error(item, "write_client_required")
    result = client.create_document_from_file(
        candidate.absolute_path,
        metadata=metadata,
        collection_ids=[collection_refs[item.collection].collection_id],
    )
    if not result.ok:
        return _error(
            item,
            result.status,
            result.message,
            r2r_write="attempted" if result.attempted else "not_performed",
            remote_state=result.remote_state,
        )
    return SyncOperationResult(
        item.action,
        item.project_id,
        item.collection,
        item.source_path,
        "created",
        "performed",
        remote_state="confirmed",
        remote_document_id=_extract_document_id(result.data),
    )


def _handle_update(item: ComparisonItem, candidate: DocumentCandidate | None, *, apply: bool) -> SyncOperationResult:
    if candidate is None:
        return _skipped(item, "candidate_missing")
    return SyncOperationResult(
        item.action,
        item.project_id,
        item.collection,
        item.source_path,
        "skipped_update",
        "not_performed",
        remote_document_id=item.remote_document_id,
        reason="content_update_endpoint_unknown",
    )


def _skipped(item: ComparisonItem, reason: str) -> SyncOperationResult:
    return SyncOperationResult(
        item.action,
        item.project_id,
        item.collection,
        item.source_path,
        f"skipped_{reason}",
        "not_performed",
        remote_document_id=item.remote_document_id,
        reason=reason,
    )


def _error(
    item: ComparisonItem,
    status: str,
    error: str | None = None,
    *,
    r2r_write: str = "not_performed",
    remote_state: str = "not_changed",
) -> SyncOperationResult:
    return SyncOperationResult(
        item.action,
        item.project_id,
        item.collection,
        item.source_path,
        "error",
        r2r_write,
        remote_state=remote_state,
        remote_document_id=item.remote_document_id,
        reason=status,
        error=error,
    )


def _skip_status_for_action(action: str) -> str:
    if action == "stale_remote":
        return "skipped_stale_remote_report_only"
    return f"skipped_{action}"


def _extract_collection_items(payload: Any) -> list[Any]:
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
        for key in ("results", "items", "collections"):
            value = current.get(key)
            if isinstance(value, list):
                return value
    return []


def _extract_document_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates = [payload]
    if isinstance(payload.get("results"), dict):
        candidates.append(payload["results"])
    if isinstance(payload.get("data"), dict):
        candidates.append(payload["data"])
    for candidate in candidates:
        value = candidate.get("document_id") or candidate.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
