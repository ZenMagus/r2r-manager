from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.git_metadata import FileMetadata, GitRepoMetadata, collect_file_metadata, collect_git_metadata
from app.project_config import MANAGER_ROOT, ProjectEntry, R2RProjectConfig
from app.project_manifest import parse_project_manifest


SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", "node_modules", "data", "var", "external", "logs", ".git"}
SKIP_SUFFIXES = {
    ".wav",
    ".flac",
    ".mp3",
    ".mp4",
    ".m4b",
    ".mkv",
    ".ts",
    ".bin",
    ".pt",
    ".pth",
    ".safetensors",
    ".onnx",
    ".sqlite",
    ".db",
    ".pyc",
}
SKIP_FILENAMES = {".env", ".env.local", ".env.example.local"}


@dataclass(frozen=True)
class DocumentCandidate:
    project_id: str
    collection: str
    source_path: str
    absolute_path: Path
    exists: bool
    action: str
    skip_reason: str | None = None
    doc_status: str | None = None
    content_sha256: str | None = None
    size_bytes: int | None = None
    modified_at: str | None = None
    git: GitRepoMetadata | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def public_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "collection": self.collection,
            "source_path": self.source_path,
            "exists": self.exists,
            "action": self.action,
            "skip_reason": self.skip_reason,
            "doc_status": self.doc_status,
            "content_sha256": self.content_sha256,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "git": None
            if self.git is None
            else {
                "git_root": self.git.git_root,
                "branch": self.git.branch,
                "commit": self.git.commit,
                "dirty": self.git.dirty,
                "remote_url": self.git.remote_url,
                "warnings": list(self.git.warnings),
            },
            "warnings": list(self.warnings),
        }


def discover_documents(config: R2RProjectConfig, *, project_ids: set[str] | None = None) -> list[DocumentCandidate]:
    candidates: list[DocumentCandidate] = []
    for project in config.projects:
        if project_ids is not None and project.project_id not in project_ids:
            continue
        candidates.extend(discover_project_documents(project))
    if project_ids is None and config.shared is not None:
        candidates.extend(discover_shared_documents(config))
    return candidates


def discover_project_documents(project: ProjectEntry) -> list[DocumentCandidate]:
    manifest = parse_project_manifest(project.resolved_path, project.manifest)
    git = collect_git_metadata(project.resolved_path)
    candidates: list[DocumentCandidate] = []
    for source_path in manifest.canonical_paths:
        absolute_path = project.resolved_path / source_path
        candidates.append(_candidate_for_path(project.project_id, project.collection, project.resolved_path, source_path, absolute_path, git, manifest.warnings))
    return candidates


def discover_shared_documents(config: R2RProjectConfig) -> list[DocumentCandidate]:
    if config.shared is None:
        return []
    root = MANAGER_ROOT
    candidates: list[DocumentCandidate] = []
    git_by_root: dict[Path, GitRepoMetadata] = {}
    for absolute_path in config.shared.files:
        source_path = os.path.relpath(absolute_path.resolve(), root.resolve())
        git_root = _nearest_git_parent(absolute_path)
        git = None
        if git_root is not None:
            git = git_by_root.setdefault(git_root, collect_git_metadata(git_root))
        candidates.append(_candidate_for_path("shared", config.shared.collection, root, source_path, absolute_path, git, ()))
    return candidates


def _candidate_for_path(
    project_id: str,
    collection: str,
    root: Path,
    source_path: str,
    absolute_path: Path,
    git: GitRepoMetadata | None,
    inherited_warnings: tuple[str, ...],
) -> DocumentCandidate:
    skip_reason = skip_reason_for_path(source_path, absolute_path)
    exists = absolute_path.is_file()
    if skip_reason is not None:
        file_meta = FileMetadata(None, None, None)
        action = "skipped"
    elif not exists:
        file_meta = FileMetadata(None, None, None, ("file_missing",))
        action = "missing"
    else:
        file_meta = collect_file_metadata(absolute_path)
        action = "would_update_unknown"
    warnings = tuple(dict.fromkeys([*inherited_warnings, *file_meta.warnings]))
    return DocumentCandidate(
        project_id=project_id,
        collection=collection,
        source_path=source_path,
        absolute_path=absolute_path,
        exists=exists,
        action=action,
        skip_reason=skip_reason,
        doc_status="candidate" if action == "would_update_unknown" else action,
        content_sha256=file_meta.content_sha256,
        size_bytes=file_meta.size_bytes,
        modified_at=file_meta.modified_at,
        git=git,
        warnings=warnings,
    )


def skip_reason_for_path(source_path: str, absolute_path: Path) -> str | None:
    parts = set(Path(source_path).parts)
    if parts & SKIP_DIRS:
        return "excluded_directory"
    if absolute_path.name in SKIP_FILENAMES or absolute_path.name.startswith(".env"):
        return "excluded_secret_or_env"
    if absolute_path.suffix.lower() in SKIP_SUFFIXES:
        return "excluded_binary_or_runtime_artifact"
    return None


def _nearest_git_parent(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None
