from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.project_config import ProjectConfigError, load_project_config


ROOT = Path(__file__).resolve().parents[1]


def test_config_loads_project_entries() -> None:
    config = load_project_config(ROOT / "config" / "projects.example.yaml")

    assert {project.project_id for project in config.projects} == {
        "edub",
        "voice-stack",
        "autodub",
        "local-runtime-manager",
    }
    voice_stack = config.get_project("voice-stack")
    assert voice_stack is not None
    assert voice_stack.collection == "voice-stack"
    assert voice_stack.path.is_symlink()
    assert voice_stack.resolved_path == (ROOT.parent / "voice-stack").resolve()


def test_config_loads_shared_docs() -> None:
    config = load_project_config(ROOT / "config" / "projects.example.yaml")

    assert config.shared is not None
    assert config.shared.collection == "shared-decisions"
    assert (ROOT.parent / "README.MD").resolve() in {path.resolve() for path in config.shared.files}


def test_config_rejects_duplicate_project_ids(tmp_path: Path) -> None:
    payload = {
        "projects": [
            {
                "project_id": "edub",
                "collection": "edub",
                "path": "projects/edub",
                "manifest": "docs/project-knowledge-manifest.md",
            },
            {
                "project_id": "edub",
                "collection": "edub",
                "path": "projects/edub",
                "manifest": "docs/project-knowledge-manifest.md",
            },
        ]
    }
    path = tmp_path / "projects.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ProjectConfigError, match="Duplicate project_id"):
        load_project_config(path)
