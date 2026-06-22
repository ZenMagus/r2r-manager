from __future__ import annotations

from pathlib import Path

from app.project_manifest import parse_project_manifest


def test_manifest_parser_extracts_canonical_docs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    (project / "README.md").write_text("# Readme\n", encoding="utf-8")
    (project / "docs" / "project-knowledge-manifest.md").write_text(
        """# Manifest

## Canonical Docs To Ingest Later

- `README.md`
- `docs/architecture.md`

## Other Section

- `docs/ignored.md`
""",
        encoding="utf-8",
    )

    manifest = parse_project_manifest(project, "docs/project-knowledge-manifest.md")

    assert manifest.canonical_paths == (
        "README.md",
        "docs/architecture.md",
        "docs/project-knowledge-manifest.md",
    )
    assert manifest.warnings == ()


def test_missing_manifest_uses_conservative_fallback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    (project / "README.md").write_text("# Readme\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

    manifest = parse_project_manifest(project, "docs/project-knowledge-manifest.md")

    assert manifest.canonical_paths == ("README.md", "AGENTS.md")
    assert manifest.warnings
