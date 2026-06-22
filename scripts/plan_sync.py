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
from app.sync_plan import build_sync_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a dry-run R2R documentation sync plan.")
    parser.add_argument("--config", default="config/projects.example.yaml")
    parser.add_argument("--project", action="append", help="Project ID to include. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Include all registered projects plus shared docs.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    parser.add_argument("--verbose", action="store_true", help="Print warnings and Git detail in text output.")
    parser.add_argument("--output", help="Optional path to write the dry-run plan JSON.")
    args = parser.parse_args()

    if not args.all and not args.project:
        parser.print_usage(sys.stderr)
        print("error: pass --all or --project PROJECT_ID", file=sys.stderr)
        return 2

    try:
        config = load_project_config(args.config)
        project_ids = None if args.all else set(args.project or [])
        if project_ids is not None:
            missing = sorted(project_id for project_id in project_ids if config.get_project(project_id) is None)
            if missing:
                print(f"error: unknown project id(s): {', '.join(missing)}", file=sys.stderr)
                return 2
        plan = build_sync_plan(config, project_ids=project_ids)
    except ProjectConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = plan.to_dict()
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(payload, verbose=args.verbose))
    return 0


def _render_text(payload: dict, *, verbose: bool) -> str:
    lines = [
        "R2R sync plan: dry-run",
        f"R2R comparison: {payload['r2r_comparison']}",
        f"R2R write: {payload['r2r_write']}",
        f"documents: {payload['summary']['total']}",
    ]
    lines.append("actions:")
    for action, count in payload["summary"]["by_action"].items():
        lines.append(f"- {action}: {count}")
    lines.append("projects:")
    for project_id, actions in payload["summary"]["by_project"].items():
        detail = ", ".join(f"{action}={count}" for action, count in actions.items())
        lines.append(f"- {project_id}: {detail}")
    lines.append("documents:")
    for doc in payload["documents"]:
        digest = doc["content_sha256"][:12] if doc["content_sha256"] else "-"
        lines.append(
            f"- {doc['project_id']} -> {doc['collection']} {doc['action']} {doc['source_path']} sha256={digest}"
        )
        if verbose:
            git = doc.get("git") or {}
            lines.append(
                f"  git branch={git.get('branch')} commit={git.get('commit')} dirty={git.get('dirty')}"
            )
            for warning in [*doc.get("warnings", []), *((git.get("warnings") or []) if git else [])]:
                lines.append(f"  warning: {warning}")
    lines.append("No R2R API calls or writes were performed.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
