from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.r2r_client import R2RReadOnlyClient
from app.sync_plan import SyncPlan


@dataclass(frozen=True)
class RemoteDocumentMetadata:
    document_id: str | None
    collection: str | None
    project_id: str | None
    source_path: str | None
    content_sha256: str | None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    raw_document: dict[str, Any] = field(default_factory=dict)

    @property
    def comparable_key(self) -> tuple[str, str, str] | None:
        if self.project_id and self.collection and self.source_path:
            return (self.project_id, self.collection, self.source_path)
        return None


@dataclass(frozen=True)
class ComparisonItem:
    action: str
    project_id: str | None
    collection: str | None
    source_path: str | None
    local_sha256: str | None = None
    remote_sha256: str | None = None
    remote_document_id: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "project_id": self.project_id,
            "collection": self.collection,
            "source_path": self.source_path,
            "local_sha256": self.local_sha256,
            "remote_sha256": self.remote_sha256,
            "remote_document_id": self.remote_document_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class R2RComparisonReport:
    mode: str
    r2r_write: str
    comparison_status: str
    items: tuple[ComparisonItem, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, Any]:
        by_action = Counter(item.action for item in self.items)
        by_project: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        by_collection: dict[str, int] = defaultdict(int)
        for item in self.items:
            by_project[item.project_id or "unknown"][item.action] += 1
            by_collection[item.collection or "unknown"] += 1
        return {
            "total": len(self.items),
            "by_action": dict(sorted(by_action.items())),
            "by_project": {project: dict(sorted(actions.items())) for project, actions in sorted(by_project.items())},
            "by_collection": dict(sorted(by_collection.items())),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "r2r_write": self.r2r_write,
            "comparison_status": self.comparison_status,
            "summary": self.summary(),
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
        }


def compare_plan_with_remote_documents(plan: SyncPlan, remote_documents: list[RemoteDocumentMetadata]) -> R2RComparisonReport:
    warnings: list[str] = []
    remote_by_key: dict[tuple[str, str, str], RemoteDocumentMetadata] = {}
    unknown_remote: list[RemoteDocumentMetadata] = []
    for remote in remote_documents:
        key = remote.comparable_key
        if key is None:
            unknown_remote.append(remote)
            continue
        remote_by_key[key] = remote

    items: list[ComparisonItem] = []
    seen_remote_keys: set[tuple[str, str, str]] = set()
    for candidate in plan.candidates:
        if candidate.action == "skipped":
            items.append(
                ComparisonItem(
                    action="skipped",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    local_sha256=candidate.content_sha256,
                    reason=candidate.skip_reason,
                )
            )
            continue
        if candidate.action == "missing":
            items.append(
                ComparisonItem(
                    action="missing_local",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    reason="local manifest-listed document is missing",
                )
            )
            continue
        key = (candidate.project_id, candidate.collection, candidate.source_path)
        remote = remote_by_key.get(key)
        if remote is None:
            items.append(
                ComparisonItem(
                    action="would_create",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    local_sha256=candidate.content_sha256,
                    reason="no comparable R2R document metadata found",
                )
            )
            continue
        seen_remote_keys.add(key)
        if not remote.content_sha256:
            items.append(
                ComparisonItem(
                    action="unknown_metadata",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    local_sha256=candidate.content_sha256,
                    remote_document_id=remote.document_id,
                    reason="remote metadata lacks content_sha256",
                )
            )
        elif remote.content_sha256 == candidate.content_sha256:
            items.append(
                ComparisonItem(
                    action="unchanged",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    local_sha256=candidate.content_sha256,
                    remote_sha256=remote.content_sha256,
                    remote_document_id=remote.document_id,
                )
            )
        else:
            items.append(
                ComparisonItem(
                    action="would_update",
                    project_id=candidate.project_id,
                    collection=candidate.collection,
                    source_path=candidate.source_path,
                    local_sha256=candidate.content_sha256,
                    remote_sha256=remote.content_sha256,
                    remote_document_id=remote.document_id,
                    reason="content_sha256 differs",
                )
            )

    for key, remote in sorted(remote_by_key.items()):
        if key not in seen_remote_keys:
            items.append(
                ComparisonItem(
                    action="stale_remote",
                    project_id=remote.project_id,
                    collection=remote.collection,
                    source_path=remote.source_path,
                    remote_sha256=remote.content_sha256,
                    remote_document_id=remote.document_id,
                    reason="R2R document metadata has no matching local plan candidate; report-only",
                )
            )

    for remote in unknown_remote:
        items.append(
            ComparisonItem(
                action="unknown_metadata",
                project_id=remote.project_id,
                collection=remote.collection,
                source_path=remote.source_path,
                remote_sha256=remote.content_sha256,
                remote_document_id=remote.document_id,
                reason="remote document lacks project_id/collection/source_path metadata",
            )
        )

    if unknown_remote:
        warnings.append(f"remote_documents_with_unusable_metadata:{len(unknown_remote)}")

    return R2RComparisonReport(
        mode="read_only_compare",
        r2r_write="not_performed",
        comparison_status="complete",
        items=tuple(items),
        warnings=tuple(warnings),
    )


def compare_plan_to_live_r2r(plan: SyncPlan, client: R2RReadOnlyClient) -> R2RComparisonReport:
    result = client.list_all_documents()
    if not result.ok:
        return R2RComparisonReport(
            mode="read_only_compare",
            r2r_write="not_performed",
            comparison_status="r2r_unavailable",
            items=(),
            warnings=(f"documents_read_failed:{result.status}",),
        )
    remote = [normalize_remote_document(item) for item in extract_result_items(result.data)]
    return compare_plan_with_remote_documents(plan, remote)


def normalize_remote_document(payload: Any) -> RemoteDocumentMetadata:
    if not isinstance(payload, dict):
        return RemoteDocumentMetadata(None, None, None, None, None, raw_document={})
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return RemoteDocumentMetadata(
        document_id=_first_str(payload, ("id", "document_id")),
        collection=_first_str(metadata, ("collection", "collection_name", "r2r_collection")),
        project_id=_first_str(metadata, ("project_id", "owner_project", "project")),
        source_path=_first_str(metadata, ("source_path", "source", "path")),
        content_sha256=_first_str(metadata, ("content_sha256", "sha256", "content_hash")),
        raw_metadata=metadata,
        raw_document=payload,
    )


def extract_result_items(payload: Any) -> list[Any]:
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


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
