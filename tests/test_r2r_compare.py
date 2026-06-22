from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

from app.document_discovery import DocumentCandidate
from app.r2r_compare import RemoteDocumentMetadata, compare_plan_with_remote_documents
from app.sync_plan import SyncPlan


ROOT = Path(__file__).resolve().parents[1]


def test_comparison_reports_would_create_when_no_matching_remote_doc() -> None:
    report = compare_plan_with_remote_documents(_plan(_candidate("README.md", "local-a")), [])

    assert report.summary()["by_action"] == {"would_create": 1}
    assert report.items[0].reason == "no comparable R2R document metadata found"


def test_comparison_reports_unchanged_when_source_path_and_hash_match() -> None:
    report = compare_plan_with_remote_documents(
        _plan(_candidate("README.md", "same")),
        [_remote("README.md", "same", document_id="remote-1")],
    )

    assert report.items[0].action == "unchanged"
    assert report.items[0].remote_document_id == "remote-1"


def test_comparison_reports_would_update_when_hash_differs() -> None:
    report = compare_plan_with_remote_documents(
        _plan(_candidate("README.md", "local-new")),
        [_remote("README.md", "remote-old")],
    )

    assert report.items[0].action == "would_update"
    assert report.items[0].reason == "content_sha256 differs"


def test_comparison_reports_unknown_metadata_when_remote_hash_missing() -> None:
    report = compare_plan_with_remote_documents(
        _plan(_candidate("README.md", "local")),
        [_remote("README.md", None)],
    )

    assert report.items[0].action == "unknown_metadata"
    assert report.items[0].reason == "remote metadata lacks content_sha256"


def test_stale_remote_docs_are_reported_only() -> None:
    report = compare_plan_with_remote_documents(
        _plan(_candidate("README.md", "local")),
        [_remote("README.md", "local"), _remote("docs/old.md", "old")],
    )

    actions = [item.action for item in report.items]
    assert "unchanged" in actions
    assert "stale_remote" in actions
    stale = next(item for item in report.items if item.action == "stale_remote")
    assert stale.reason == "R2R document metadata has no matching local plan candidate; report-only"


def test_remote_doc_without_usable_metadata_is_reported() -> None:
    report = compare_plan_with_remote_documents(
        _plan(_candidate("README.md", "local")),
        [RemoteDocumentMetadata("remote-unknown", None, None, None, "hash")],
    )

    assert "remote_documents_with_unusable_metadata:1" in report.warnings
    assert any(item.action == "unknown_metadata" for item in report.items)


def test_compare_cli_unreachable_uses_read_only_probe_and_exits_nonzero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_r2r.py",
            "--config",
            "config/projects.example.yaml",
            "--project",
            "voice-stack",
            "--base-url",
            "http://127.0.0.1:1",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["comparison_status"] == "r2r_unreachable"
    assert payload["r2r_write"] == "not_performed"


def test_list_all_documents_paginates_with_fake_http_client() -> None:
    from app.r2r_client import R2RReadOnlyClient
    from app.r2r_config import R2RConfig

    class FakeHttpClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get(self, endpoint: str, *, headers: dict[str, str]):
            self.calls.append(endpoint)
            if "offset=0" in endpoint:
                return _response(endpoint, {"results": {"results": [{"id": "one"}], "total_entries": 2}})
            return _response(endpoint, {"results": {"results": [{"id": "two"}], "total_entries": 2}})

    fake = FakeHttpClient()
    result = R2RReadOnlyClient(R2RConfig("http://r2r.test", 1.0), client=fake).list_all_documents(page_size=1)

    assert result.ok is True
    assert result.data["results"] == [{"id": "one"}, {"id": "two"}]
    assert len(fake.calls) == 2


def _candidate(source_path: str, sha: str) -> DocumentCandidate:
    return DocumentCandidate(
        project_id="voice-stack",
        collection="voice-stack",
        source_path=source_path,
        absolute_path=Path("/tmp") / source_path,
        exists=True,
        action="would_update_unknown",
        doc_status="candidate",
        content_sha256=sha,
    )


def _remote(source_path: str, sha: str | None, *, document_id: str = "remote") -> RemoteDocumentMetadata:
    return RemoteDocumentMetadata(
        document_id=document_id,
        collection="voice-stack",
        project_id="voice-stack",
        source_path=source_path,
        content_sha256=sha,
    )


def _plan(*candidates: DocumentCandidate) -> SyncPlan:
    return SyncPlan("dry_run", "not_performed_future_work", "not_performed", candidates)


def _response(endpoint: str, data: dict, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", endpoint), json=data)
