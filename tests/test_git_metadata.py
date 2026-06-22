from __future__ import annotations

import subprocess
from pathlib import Path

from app.git_metadata import collect_file_metadata, collect_git_metadata


def test_content_sha256_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("hello\n", encoding="utf-8")

    first = collect_file_metadata(path)
    second = collect_file_metadata(path)

    assert first.content_sha256 == second.content_sha256
    assert first.size_bytes == 6


def test_git_metadata_handles_clean_mocked_repo(tmp_path: Path) -> None:
    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        outputs = {
            ("git", "rev-parse", "--show-toplevel"): "/repo\n",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "rev-parse", "HEAD"): "abc123\n",
            ("git", "status", "--porcelain"): "",
            ("git", "config", "--get", "remote.origin.url"): "git@example.invalid:repo.git\n",
        }
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    metadata = collect_git_metadata(tmp_path, runner=runner)

    assert metadata.git_root == "/repo"
    assert metadata.branch == "main"
    assert metadata.commit == "abc123"
    assert metadata.dirty is False
    assert metadata.remote_url == "git@example.invalid:repo.git"
    assert metadata.warnings == ()


def test_git_metadata_handles_dirty_mocked_repo(tmp_path: Path) -> None:
    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        outputs = {
            ("git", "rev-parse", "--show-toplevel"): "/repo\n",
            ("git", "branch", "--show-current"): "main\n",
            ("git", "rev-parse", "HEAD"): "abc123\n",
            ("git", "status", "--porcelain"): " M README.md\n",
            ("git", "config", "--get", "remote.origin.url"): "",
        }
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command)], "")

    metadata = collect_git_metadata(tmp_path, runner=runner)

    assert metadata.dirty is True


def test_git_metadata_failure_returns_warning(tmp_path: Path) -> None:
    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 128, "", "fatal")

    metadata = collect_git_metadata(tmp_path, runner=runner)

    assert metadata.git_root is None
    assert metadata.warnings
