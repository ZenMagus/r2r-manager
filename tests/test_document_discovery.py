from __future__ import annotations

from pathlib import Path

from app.document_discovery import discover_documents, skip_reason_for_path
from app.project_config import load_project_config


ROOT = Path(__file__).resolve().parents[1]


def test_document_discovery_includes_manifest_core_docs() -> None:
    config = load_project_config(ROOT / "config" / "projects.example.yaml")

    docs = discover_documents(config, project_ids={"voice-stack"})
    source_paths = {doc.source_path for doc in docs}

    assert "README.md" in source_paths
    assert "AGENTS.md" in source_paths
    assert "docs/project-knowledge-manifest.md" in source_paths
    assert all(doc.project_id == "voice-stack" for doc in docs)


def test_document_discovery_includes_shared_docs() -> None:
    config = load_project_config(ROOT / "config" / "projects.example.yaml")

    docs = discover_documents(config)
    shared = [doc for doc in docs if doc.project_id == "shared"]

    assert {doc.collection for doc in shared} == {"shared-decisions"}
    assert any(doc.source_path.endswith("README.MD") for doc in shared)
    assert any(doc.source_path.endswith("r2r-prep.md") for doc in shared)


def test_binary_generated_paths_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "data" / "audio.wav"

    assert skip_reason_for_path("data/audio.wav", path) == "excluded_directory"
    assert skip_reason_for_path("docs/sample.wav", tmp_path / "docs" / "sample.wav") == "excluded_binary_or_runtime_artifact"
    assert skip_reason_for_path(".env", tmp_path / ".env") == "excluded_secret_or_env"
