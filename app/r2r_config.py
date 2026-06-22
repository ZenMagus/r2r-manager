from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_R2R_BASE_URL = "http://localhost:7272"
DEFAULT_R2R_TIMEOUT_SECONDS = 5.0
DEFAULT_R2R_WRITE_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class R2RConfig:
    base_url: str
    timeout_seconds: float
    api_key: str | None = None
    write_timeout_seconds: float = DEFAULT_R2R_WRITE_TIMEOUT_SECONDS


def get_r2r_config() -> R2RConfig:
    return R2RConfig(
        base_url=os.getenv("R2R_BASE_URL", DEFAULT_R2R_BASE_URL).rstrip("/"),
        timeout_seconds=float(os.getenv("R2R_TIMEOUT_SECONDS", str(DEFAULT_R2R_TIMEOUT_SECONDS))),
        api_key=os.getenv("R2R_API_KEY") or os.getenv("R2R_TOKEN") or None,
        write_timeout_seconds=float(os.getenv("R2R_WRITE_TIMEOUT_SECONDS", str(DEFAULT_R2R_WRITE_TIMEOUT_SECONDS))),
    )
