from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


MANAGER_ROOT = Path(__file__).resolve().parents[1]


class ProjectConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectEntry:
    project_id: str
    collection: str
    path: Path
    resolved_path: Path
    manifest: str


@dataclass(frozen=True)
class SharedConfig:
    collection: str
    files: tuple[Path, ...]


@dataclass(frozen=True)
class R2RProjectConfig:
    config_path: Path
    projects: tuple[ProjectEntry, ...]
    shared: SharedConfig | None = None

    def get_project(self, project_id: str) -> ProjectEntry | None:
        for project in self.projects:
            if project.project_id == project_id:
                return project
        return None


def load_project_config(path: str | Path = "config/projects.example.yaml") -> R2RProjectConfig:
    config_path = _resolve_manager_path(path)
    if not config_path.is_file():
        raise ProjectConfigError(f"Project config was not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ProjectConfigError("Project config must be a mapping.")

    projects_payload = payload.get("projects") or []
    if not isinstance(projects_payload, list):
        raise ProjectConfigError("projects must be a list.")

    projects = tuple(_load_project_entry(item) for item in projects_payload)
    _validate_unique_project_ids(projects)
    shared = _load_shared(payload.get("shared"))
    return R2RProjectConfig(config_path=config_path, projects=projects, shared=shared)


def _load_project_entry(payload: Any) -> ProjectEntry:
    if not isinstance(payload, dict):
        raise ProjectConfigError("Project entry must be a mapping.")
    project_id = _required_str(payload, "project_id")
    collection = _required_str(payload, "collection")
    manifest = _required_str(payload, "manifest")
    configured_path = _resolve_manager_path(_required_str(payload, "path"))
    resolved_path = configured_path.resolve()
    if not configured_path.exists():
        raise ProjectConfigError(f"Project path does not exist for {project_id}: {configured_path}")
    if not _is_registered_project_path(configured_path):
        raise ProjectConfigError(f"Project path must be under r2r-manager/projects: {configured_path}")
    expected_root = (MANAGER_ROOT.parent / project_id).resolve()
    if resolved_path != expected_root:
        raise ProjectConfigError(f"Project symlink for {project_id} resolves to {resolved_path}, expected {expected_root}")
    return ProjectEntry(
        project_id=project_id,
        collection=collection,
        path=configured_path,
        resolved_path=resolved_path,
        manifest=manifest,
    )


def _load_shared(payload: Any) -> SharedConfig | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ProjectConfigError("shared must be a mapping.")
    collection = _required_str(payload, "collection")
    files_payload = payload.get("files") or []
    if not isinstance(files_payload, list) or not all(isinstance(item, str) and item.strip() for item in files_payload):
        raise ProjectConfigError("shared.files must be a list of non-empty strings.")
    return SharedConfig(collection=collection, files=tuple(_resolve_manager_path(item.strip()) for item in files_payload))


def _resolve_manager_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = MANAGER_ROOT / candidate
    return candidate


def _is_registered_project_path(path: Path) -> bool:
    try:
        path.relative_to(MANAGER_ROOT / "projects")
        return True
    except ValueError:
        return False


def _validate_unique_project_ids(projects: tuple[ProjectEntry, ...]) -> None:
    seen: set[str] = set()
    for project in projects:
        if project.project_id in seen:
            raise ProjectConfigError(f"Duplicate project_id: {project.project_id}")
        seen.add(project.project_id)


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"Project config requires non-empty {key}.")
    return value.strip()
