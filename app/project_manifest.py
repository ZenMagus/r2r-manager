from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


CANONICAL_HEADING = "canonical docs to ingest later"
FALLBACK_DOCS = ("README.md", "AGENTS.md", "docs/project-knowledge-manifest.md")


@dataclass(frozen=True)
class ProjectManifest:
    manifest_path: Path
    canonical_paths: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def parse_project_manifest(project_root: Path, manifest_relative_path: str) -> ProjectManifest:
    manifest_path = project_root / manifest_relative_path
    if not manifest_path.is_file():
        return ProjectManifest(
            manifest_path=manifest_path,
            canonical_paths=tuple(path for path in FALLBACK_DOCS if (project_root / path).is_file()),
            warnings=(f"manifest_missing:{manifest_relative_path}; using conservative fallback docs",),
        )

    text = manifest_path.read_text(encoding="utf-8")
    canonical = _extract_canonical_paths(text)
    warnings: list[str] = []
    if not canonical:
        canonical = [path for path in FALLBACK_DOCS if (project_root / path).is_file()]
        warnings.append("canonical_doc_list_not_found; using conservative fallback docs")
    if manifest_relative_path not in canonical and manifest_path.is_file():
        canonical.append(manifest_relative_path)
    return ProjectManifest(manifest_path=manifest_path, canonical_paths=tuple(dict.fromkeys(canonical)), warnings=tuple(warnings))


def _extract_canonical_paths(text: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    paths: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            if in_section and heading != CANONICAL_HEADING:
                break
            in_section = heading == CANONICAL_HEADING
            continue
        if not in_section or not stripped.startswith("- "):
            continue
        item = stripped[2:].strip()
        if item.startswith("`") and item.endswith("`"):
            item = item[1:-1]
        if _looks_like_doc_path(item):
            paths.append(item)
    return paths


def _looks_like_doc_path(value: str) -> bool:
    if value.startswith(("/", "../")):
        return False
    if any(part in value for part in ("*", "\x00")):
        return False
    return value.endswith((".md", ".yaml", ".yml")) or value in {"README.md", "README.MD", "AGENTS.md"}
