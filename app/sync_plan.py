from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.document_discovery import DocumentCandidate, discover_documents
from app.project_config import R2RProjectConfig


@dataclass(frozen=True)
class SyncPlan:
    mode: str
    r2r_comparison: str
    r2r_write: str
    candidates: tuple[DocumentCandidate, ...]

    def summary(self) -> dict[str, Any]:
        by_action = Counter(candidate.action for candidate in self.candidates)
        by_project: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        by_collection: dict[str, int] = defaultdict(int)
        for candidate in self.candidates:
            by_project[candidate.project_id][candidate.action] += 1
            by_collection[candidate.collection] += 1
        return {
            "total": len(self.candidates),
            "by_action": dict(sorted(by_action.items())),
            "by_project": {project: dict(sorted(actions.items())) for project, actions in sorted(by_project.items())},
            "by_collection": dict(sorted(by_collection.items())),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "r2r_comparison": self.r2r_comparison,
            "r2r_write": self.r2r_write,
            "summary": self.summary(),
            "documents": [candidate.public_dict() for candidate in self.candidates],
        }


def build_sync_plan(config: R2RProjectConfig, *, project_ids: set[str] | None = None) -> SyncPlan:
    candidates = tuple(discover_documents(config, project_ids=project_ids))
    return SyncPlan(
        mode="dry_run",
        r2r_comparison="not_performed_future_work",
        r2r_write="not_performed",
        candidates=candidates,
    )
