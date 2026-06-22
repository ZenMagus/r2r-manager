from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

from app.document_discovery import DocumentCandidate
from app.r2r_client import R2RReadOnlyClient, R2RWriteClient
from app.r2r_compare import ComparisonItem, R2RComparisonReport
from app.r2r_config import R2RConfig
from app.r2r_sync import build_ingest_metadata, build_sync_report
from app.sync_plan import SyncPlan


ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_does_not_call_mutating_client_methods(tmp_path: Path) -> None:
    source = _source(tmp_path)
    client = R2RReadOnlyClient(_config(), client=FakeHttpClient())
    report = build_sync_report(_plan(_candidate(source)), _comparison(_item("would_create")), client=client, apply=False)

    assert report.r2r_write == "not_performed"
    assert report.operations[0].status == "dry_run"
    assert client._client.posts == []


def test_apply_create_calls_create_method_only_for_would_create(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient()
    client = R2RWriteClient(_config(), client=fake)
    report = build_sync_report(_plan(_candidate(source)), _comparison(_item("would_create")), client=client, apply=True)

    assert report.r2r_write == "performed"
    assert report.operations[0].status == "created"
    assert len(fake.posts) == 1
    assert fake.posts[0]["endpoint"] == "http://r2r.test/v3/documents"
    assert json.loads(fake.posts[0]["data"]["collection_ids"]) == ["collection-voice-stack"]
    metadata = json.loads(fake.posts[0]["data"]["metadata"])
    assert metadata["project_id"] == "voice-stack"
    assert metadata["collection"] == "voice-stack"
    assert metadata["source_path"] == "README.md"
    assert metadata["content_sha256"] == "abc123"
    assert metadata["git_root"] == "/repo/voice-stack"
    assert metadata["git_branch"] == "main"
    assert metadata["git_commit"] == "deadbeef"
    assert metadata["ingest_tool"] == "r2r-manager"


def test_timeout_reports_attempted_write_and_unknown_remote_state(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient(create_exception=httpx.ReadTimeout("timed out"))
    report = build_sync_report(
        _plan(_candidate(source)),
        _comparison(_item("would_create")),
        client=R2RWriteClient(_config(), client=fake),
        apply=True,
    )

    assert report.r2r_write == "attempted"
    assert report.remote_state == "unknown"
    assert report.operations[0].r2r_write == "attempted"
    assert report.operations[0].remote_state == "unknown"
    assert len(fake.posts) == 1


def test_yaml_is_uploaded_as_text_with_safe_filename(tmp_path: Path) -> None:
    source = tmp_path / "capabilities.registry.yaml"
    source.write_text("capabilities: []\n", encoding="utf-8")
    fake = FakeHttpClient()
    report = build_sync_report(
        _plan(_candidate(source, source_path="docs/capabilities.registry.yaml")),
        _comparison(_item("would_create", source_path="docs/capabilities.registry.yaml")),
        client=R2RWriteClient(_config(), client=fake),
        apply=True,
    )

    assert report.operations[0].status == "created"
    upload_name, _handle, content_type = fake.posts[0]["files"]["file"]
    assert upload_name == "capabilities.registry.yaml.txt"
    assert content_type == "text/plain"
    metadata = json.loads(fake.posts[0]["data"]["metadata"])
    assert metadata["source_path"] == "docs/capabilities.registry.yaml"
    assert metadata["content_sha256"] == "abc123"


def test_would_update_is_skipped_because_content_update_endpoint_is_unknown(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient()
    client = R2RWriteClient(_config(), client=fake)
    report = build_sync_report(_plan(_candidate(source)), _comparison(_item("would_update", remote_document_id="remote-1")), client=client, apply=True)

    assert report.r2r_write == "not_performed"
    assert report.operations[0].status == "skipped_update"
    assert report.operations[0].reason == "content_update_endpoint_unknown"
    assert fake.posts == []
    assert fake.puts == []


def test_unchanged_unknown_and_stale_remote_are_skipped(tmp_path: Path) -> None:
    source = _source(tmp_path)
    comparison = _comparison(
        _item("unchanged"),
        _item("unknown_metadata"),
        _item("stale_remote", source_path="docs/old.md"),
    )
    fake = FakeHttpClient()
    report = build_sync_report(_plan(_candidate(source)), comparison, client=R2RWriteClient(_config(), client=fake), apply=True)

    assert [operation.status for operation in report.operations] == [
        "skipped_unchanged",
        "skipped_unknown_metadata",
        "skipped_stale_remote_report_only",
    ]
    assert fake.posts == []


def test_unchanged_after_partial_prior_ingestion_is_not_retried(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient()
    report = build_sync_report(
        _plan(_candidate(source)),
        _comparison(_item("unchanged", remote_document_id="already-ingested")),
        client=R2RWriteClient(_config(), client=fake),
        apply=True,
    )

    assert report.operations[0].status == "skipped_unchanged"
    assert report.r2r_write == "not_performed"
    assert fake.posts == []


def test_missing_collection_is_reported_and_not_auto_created(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient(collections=[])
    report = build_sync_report(_plan(_candidate(source)), _comparison(_item("would_create")), client=R2RWriteClient(_config(), client=fake), apply=True)

    assert report.operations[0].status == "skipped_missing_collection"
    assert report.operations[0].reason == "missing_collection"
    assert fake.posts == []


def test_failed_create_is_reported_without_stopping_other_operations(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeHttpClient(create_status_code=500)
    comparison = _comparison(_item("would_create"), _item("stale_remote", source_path="docs/old.md"))
    report = build_sync_report(_plan(_candidate(source)), comparison, client=R2RWriteClient(_config(), client=fake), apply=True)

    assert report.summary()["errors"] == 1
    assert report.operations[0].status == "error"
    assert report.operations[1].status == "skipped_stale_remote_report_only"


def test_ingest_metadata_payload_contains_required_fields(tmp_path: Path) -> None:
    metadata = build_ingest_metadata(_candidate(_source(tmp_path)), sync_mode="dry_run")

    expected = {
        "project_id",
        "collection",
        "source_path",
        "content_sha256",
        "git_root",
        "git_branch",
        "git_commit",
        "git_dirty",
        "source_mtime",
        "source_modified_time",
        "source_size_bytes",
        "r2r_manager_version",
        "schema_version",
        "ingest_tool",
        "ingest_mode",
        "sync_mode",
    }
    assert expected <= metadata.keys()


def test_apply_cli_dry_run_unreachable_makes_no_writes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/apply_r2r_sync.py",
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
    assert payload["mode"] == "dry_run"
    assert payload["r2r_write"] == "not_performed"
    assert payload["sync_status"] == "r2r_unreachable"


class FakeHttpClient:
    def __init__(
        self,
        *,
        collections: list[dict] | None = None,
        create_status_code: int = 202,
        create_exception: Exception | None = None,
    ) -> None:
        self.collections = collections if collections is not None else [{"id": "collection-voice-stack", "name": "voice-stack"}]
        self.create_status_code = create_status_code
        self.create_exception = create_exception
        self.posts: list[dict] = []
        self.puts: list[dict] = []

    def get(self, endpoint: str, *, headers: dict[str, str]):
        if "/v3/collections" in endpoint:
            return _response(endpoint, {"results": {"results": self.collections, "total_entries": len(self.collections)}})
        if "/v3/health" in endpoint:
            return _response(endpoint, {"results": {"message": "ok"}})
        if "/v3/documents" in endpoint:
            return _response(endpoint, {"results": []})
        return _response(endpoint, {"detail": "missing"}, status_code=404)

    def post(self, endpoint: str, *, headers: dict[str, str], data: dict[str, str], files: dict):
        self.posts.append({"endpoint": endpoint, "headers": headers, "data": data, "files": files})
        if self.create_exception is not None:
            raise self.create_exception
        return _response(endpoint, {"results": {"document_id": "created-doc"}}, status_code=self.create_status_code)

    def put(self, endpoint: str, *, headers: dict[str, str], content: str):
        self.puts.append({"endpoint": endpoint, "headers": headers, "content": content})
        return _response(endpoint, {"results": {"id": "updated-doc"}})


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "README.md"
    source.write_text("# Test\n", encoding="utf-8")
    return source


def _candidate(source: Path, *, source_path: str = "README.md") -> DocumentCandidate:
    from app.git_metadata import GitRepoMetadata

    return DocumentCandidate(
        project_id="voice-stack",
        collection="voice-stack",
        source_path=source_path,
        absolute_path=source,
        exists=True,
        action="would_update_unknown",
        doc_status="candidate",
        content_sha256="abc123",
        size_bytes=7,
        modified_at="2026-06-22T00:00:00Z",
        git=GitRepoMetadata("/repo/voice-stack", "main", "deadbeef", False, None),
    )


def _item(action: str, *, source_path: str = "README.md", remote_document_id: str | None = None) -> ComparisonItem:
    return ComparisonItem(
        action=action,
        project_id="voice-stack",
        collection="voice-stack",
        source_path=source_path,
        local_sha256="abc123",
        remote_sha256="old",
        remote_document_id=remote_document_id,
    )


def _comparison(*items: ComparisonItem) -> R2RComparisonReport:
    return R2RComparisonReport("read_only_compare", "not_performed", "complete", tuple(items))


def _plan(*candidates: DocumentCandidate) -> SyncPlan:
    return SyncPlan("dry_run", "performed", "not_performed", candidates)


def _config() -> R2RConfig:
    return R2RConfig("http://r2r.test", 1.0)


def _response(endpoint: str, data: dict, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", endpoint), json=data)
