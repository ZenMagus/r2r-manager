from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class GitRepoMetadata:
    git_root: str | None
    branch: str | None
    commit: str | None
    dirty: bool | None
    remote_url: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FileMetadata:
    content_sha256: str | None
    size_bytes: int | None
    modified_at: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


def default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def collect_git_metadata(repo_path: Path, *, runner: CommandRunner = default_runner) -> GitRepoMetadata:
    warnings: list[str] = []
    git_root = _git_output(["git", "rev-parse", "--show-toplevel"], repo_path, runner, warnings)
    branch = _git_output(["git", "branch", "--show-current"], repo_path, runner, warnings)
    commit = _git_output(["git", "rev-parse", "HEAD"], repo_path, runner, warnings)
    status = _git_output(["git", "status", "--porcelain"], repo_path, runner, warnings, allow_empty=True)
    remote_url = _git_output(["git", "config", "--get", "remote.origin.url"], repo_path, runner, warnings, allow_empty=True)
    return GitRepoMetadata(
        git_root=git_root,
        branch=branch or None,
        commit=commit,
        dirty=None if status is None else bool(status.strip()),
        remote_url=remote_url or None,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def collect_file_metadata(path: Path) -> FileMetadata:
    if not path.is_file():
        return FileMetadata(content_sha256=None, size_bytes=None, modified_at=None, warnings=("file_missing",))
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
    except OSError as exc:
        return FileMetadata(content_sha256=None, size_bytes=None, modified_at=None, warnings=(f"file_read_error:{type(exc).__name__}",))
    modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return FileMetadata(content_sha256=digest.hexdigest(), size_bytes=stat.st_size, modified_at=modified)


def _git_output(
    command: list[str],
    cwd: Path,
    runner: CommandRunner,
    warnings: list[str],
    *,
    allow_empty: bool = False,
) -> str | None:
    try:
        result = runner(command, cwd)
    except OSError as exc:
        warnings.append(f"git_command_failed:{command[-1]}:{type(exc).__name__}")
        return None
    if result.returncode != 0:
        warnings.append(f"git_command_failed:{command[-1]}:{result.returncode}")
        return None
    output = result.stdout.strip()
    if not output and not allow_empty:
        warnings.append(f"git_command_empty:{command[-1]}")
        return None
    return output
