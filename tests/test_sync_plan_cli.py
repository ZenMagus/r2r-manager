from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.project_config import load_project_config
from app.sync_plan import build_sync_plan


ROOT = Path(__file__).resolve().parents[1]


def test_sync_plan_marks_r2r_comparison_future() -> None:
    config = load_project_config(ROOT / "config" / "projects.example.yaml")

    plan = build_sync_plan(config, project_ids={"voice-stack"})
    payload = plan.to_dict()

    assert payload["mode"] == "dry_run"
    assert payload["r2r_comparison"] == "not_performed_future_work"
    assert payload["r2r_write"] == "not_performed"
    assert payload["documents"]
    assert {doc["project_id"] for doc in payload["documents"]} == {"voice-stack"}


def test_plan_sync_all_produces_plan_without_r2r_calls() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/plan_sync.py", "--config", "config/projects.example.yaml", "--all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "R2R sync plan: dry-run" in result.stdout
    assert "No R2R API calls or writes were performed." in result.stdout
    assert "voice-stack" in result.stdout


def test_plan_sync_project_json_limits_output() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_sync.py",
            "--config",
            "config/projects.example.yaml",
            "--project",
            "voice-stack",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert {doc["project_id"] for doc in payload["documents"]} == {"voice-stack"}
    assert payload["r2r_write"] == "not_performed"


def test_plan_sync_requires_project_or_all() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/plan_sync.py", "--config", "config/projects.example.yaml"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "pass --all or --project PROJECT_ID" in result.stderr
