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
from app.r2r_client import R2RReadOnlyClient, R2RWriteClient  # noqa: E402
from app.r2r_compare import compare_plan_to_live_r2r  # noqa: E402
from app.r2r_config import R2RConfig, get_r2r_config  # noqa: E402
from app.r2r_probe import probe_r2r  # noqa: E402
from app.r2r_sync import build_sync_report  # noqa: E402
from app.sync_plan import build_sync_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or apply cautious R2R document create/update sync.")
    parser.add_argument("--config", default="config/projects.example.yaml")
    parser.add_argument("--project", action="append", help="Project ID to include. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Include all registered projects plus shared docs.")
    parser.add_argument("--base-url", help="Override R2R base URL.")
    parser.add_argument("--apply", action="store_true", help="Perform eligible R2R creates. Omit for dry-run.")
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
        write_timeout_seconds=env_config.write_timeout_seconds,
    )
    client = R2RWriteClient(r2r_config) if args.apply else R2RReadOnlyClient(r2r_config)
    probe = probe_r2r(client)
    if not probe.reachable:
        payload = {
            "mode": "apply" if args.apply else "dry_run",
            "r2r_write": "not_performed",
            "remote_state": "not_changed",
            "sync_status": "r2r_unreachable",
            "probe": probe.to_dict(),
            "summary": {"total": 0, "created": 0, "updated": 0, "skipped": 0, "stale_remote_report_only": 0, "errors": 0, "by_status": {}, "by_action": {}, "by_project": {}},
            "operations": [],
            "warnings": ["r2r_unreachable"],
        }
        _print(payload, json_output=args.json)
        return 1

    plan = build_sync_plan(project_config, project_ids=project_ids)
    comparison = compare_plan_to_live_r2r(plan, client)
    if comparison.comparison_status != "complete":
        payload = {
            "mode": "apply" if args.apply else "dry_run",
            "r2r_write": "not_performed",
            "remote_state": "not_changed",
            "sync_status": comparison.comparison_status,
            "probe": probe.to_dict(),
            "comparison": comparison.to_dict(),
            "summary": {"total": 0, "created": 0, "updated": 0, "skipped": 0, "stale_remote_report_only": 0, "errors": 0, "by_status": {}, "by_action": {}, "by_project": {}},
            "operations": [],
            "warnings": list(comparison.warnings),
        }
        _print(payload, json_output=args.json)
        return 1

    report = build_sync_report(plan, comparison, client=client, apply=args.apply)
    payload = report.to_dict()
    payload["sync_status"] = "complete"
    payload["probe"] = probe.to_dict()
    payload["comparison"] = comparison.to_dict()
    _print(payload, json_output=args.json)
    return 0 if report.summary()["errors"] == 0 else 1


def _print(payload: dict, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(_render_text(payload))


def _render_text(payload: dict) -> str:
    lines = [
        "R2R cautious sync",
        f"sync_status: {payload['sync_status']}",
        f"mode: {payload['mode']}",
        f"r2r_write: {payload['r2r_write']}",
        f"remote_state: {payload['remote_state']}",
        f"base_url: {payload.get('probe', {}).get('base_url')}",
        f"operations: {payload['summary']['total']}",
        f"created: {payload['summary']['created']}",
        f"updated: {payload['summary']['updated']}",
        f"skipped: {payload['summary']['skipped']}",
        f"stale_remote_report_only: {payload['summary']['stale_remote_report_only']}",
        f"errors: {payload['summary']['errors']}",
        "statuses:",
    ]
    for status, count in payload["summary"]["by_status"].items():
        lines.append(f"- {status}: {count}")
    lines.append("operations:")
    for operation in payload["operations"]:
        reason = f" reason={operation.get('reason')}" if operation.get("reason") else ""
        lines.append(
            f"- {operation.get('project_id')} -> {operation.get('collection')} {operation['action']} {operation['status']} {operation.get('source_path')}{reason}"
        )
    if payload.get("warnings"):
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    if payload["mode"] == "dry_run":
        lines.append("Dry-run only: no R2R mutating endpoints were called.")
    else:
        lines.append("Apply mode: only eligible creates were attempted; delete/archive/stale mutations are not implemented.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
