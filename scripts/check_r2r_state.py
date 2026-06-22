#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.r2r_client import R2RReadOnlyClient  # noqa: E402
from app.r2r_config import R2RConfig, get_r2r_config  # noqa: E402
from app.r2r_probe import probe_r2r  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local R2R read-only API state.")
    parser.add_argument("--base-url", help="Override R2R base URL.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    args = parser.parse_args()

    env_config = get_r2r_config()
    config = R2RConfig(
        base_url=(args.base_url or env_config.base_url).rstrip("/"),
        timeout_seconds=env_config.timeout_seconds,
        api_key=env_config.api_key,
        write_timeout_seconds=env_config.write_timeout_seconds,
    )
    report = probe_r2r(R2RReadOnlyClient(config))
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(payload))
    return 0 if report.reachable else 1


def _render_text(payload: dict) -> str:
    lines = [
        "R2R read-only probe",
        f"base_url: {payload['base_url']}",
        f"reachable: {payload['reachable']}",
        f"auth_required: {payload['auth_required']}",
        f"openapi_available: {payload['openapi_available']}",
        f"collections_supported: {payload['collections_supported']}",
        f"documents_supported: {payload['documents_supported']}",
        f"metadata_supported: {payload['metadata_supported']}",
        f"archive_or_inactive_evidence: {payload['archive_or_inactive_evidence']}",
        f"delete_supported_evidence: {payload['delete_supported_evidence']}",
        f"update_supported_evidence: {payload['update_supported_evidence']}",
    ]
    if payload["warnings"]:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    if payload["notes"]:
        lines.append("notes:")
        lines.extend(f"- {note}" for note in payload["notes"])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
