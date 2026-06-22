#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.project_config import ProjectConfigError, load_project_config  # noqa: E402
from app.r2r_client import R2RReadOnlyClient  # noqa: E402
from app.r2r_compare import compare_plan_to_live_r2r  # noqa: E402
from app.r2r_config import R2RConfig, get_r2r_config  # noqa: E402
from app.r2r_probe import probe_r2r  # noqa: E402
from app.sync_plan import build_sync_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local doc sync plan to R2R read-only document metadata.")
    parser.add_argument("--config", default="config/projects.example.yaml")
    parser.add_argument("--project", action="append", help="Project ID to include. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Include all registered projects plus shared docs.")
    parser.add_argument("--base-url", help="Override R2R base URL.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    args = parser.parse_args()

    if not args.all and not args.project:
        parser.print_usage(sys.stderr)
        print("error: pass --all or --project PROJECT_ID", file=sys.stderr)
        return 2

    try:
        project_config = load_project_config(args.config)
    except ProjectConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    project_ids = None if args.all else set(args.project or [])
    if project_ids is not None:
        missing = sorted(project_id for project_id in project_ids if project_config.get_project(project_id) is None)
        if missing:
            print(f"error: unknown project id(s): {', '.join(missing)}", file=sys.stderr)
            return 2

    env_config = get_r2r_config()
    r2r_config = R2RConfig(
        base_url=(args.base_url or env_config.base_url).rstrip("/"),
        timeout_seconds=env_config.timeout_seconds,
        api_key=env_config.api_key,
    )
    client = R2RReadOnlyClient(r2r_config)
    probe = probe_r2r(client)
    if not probe.reachable:
        payload = {
            "mode": "read_only_compare",
            "r2r_write": "not_performed",
            "comparison_status": "r2r_unreachable",
            "probe": probe.to_dict(),
            "summary": {"total": 0, "by_action": {}, "by_project": {}, "by_collection": {}},
            "items": [],
            "warnings": ["r2r_unreachable"],
        }
        _print(payload, json_output=args.json)
        return 1

    plan = build_sync_plan(project_config, project_ids=project_ids)
    report = compare_plan_to_live_r2r(plan, client)
    payload = report.to_dict()
    payload["probe"] = probe.to_dict()
    _print(payload, json_output=args.json)
    return 0


def _print(payload: dict, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(_render_text(payload))


def _render_text(payload: dict) -> str:
    lines = [
        "R2R read-only comparison",
        f"comparison_status: {payload['comparison_status']}",
        f"r2r_write: {payload['r2r_write']}",
        f"base_url: {payload.get('probe', {}).get('base_url')}",
        f"items: {payload['summary']['total']}",
        "actions:",
    ]
    for action, count in payload["summary"]["by_action"].items():
        lines.append(f"- {action}: {count}")
    lines.append("projects:")
    for project_id, actions in payload["summary"]["by_project"].items():
        detail = ", ".join(f"{action}={count}" for action, count in actions.items())
        lines.append(f"- {project_id}: {detail}")
    lines.append("items:")
    for item in payload["items"]:
        local = (item.get("local_sha256") or "-")[:12]
        remote = (item.get("remote_sha256") or "-")[:12]
        lines.append(
            f"- {item.get('project_id')} -> {item.get('collection')} {item['action']} {item.get('source_path')} local={local} remote={remote}"
        )
    if payload.get("warnings"):
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    lines.append("No R2R API writes, ingestion, updates, deletes, archives, or collection creation were performed.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
