"""Centralized configuration definitions for runtime, tools, and integrations."""
<<<<<<< HEAD

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return list(default or [])
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return list(default or [])
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class AppConfig:
    """Small environment-backed configuration object used across the project."""

    log_path: str = field(default_factory=lambda: _get_env("LOG_PATH", "./app.log"))
    monitor_log_pattern: str = field(
        default_factory=lambda: _get_env("MONITOR_LOG_PATTERN", r"ERROR|Exception|Traceback")
    )
    monitor_check_interval: int = field(default_factory=lambda: _get_env_int("MONITOR_CHECK_INTERVAL", 10))
    monitor_max_log_size: int = field(default_factory=lambda: _get_env_int("MONITOR_MAX_LOG_SIZE", 1_048_576))
    healthcheck_urls: list[str] = field(default_factory=lambda: _get_env_list("HEALTHCHECK_URLS"))
    healthcheck_timeout: int = field(default_factory=lambda: _get_env_int("HEALTHCHECK_TIMEOUT", 5))
    max_iterations: int = field(default_factory=lambda: _get_env_int("MAX_ITERATIONS", 3))
    stage_one_dedup_ttl_sec: int = field(default_factory=lambda: _get_env_int("STAGE_ONE_DEDUP_TTL_SEC", 3600))
    default_service_name: str = field(default_factory=lambda: _get_env("DEFAULT_SERVICE_NAME", "demo-web-service"))
    default_repo_url: str = field(
        default_factory=lambda: _get_env(
            "DEFAULT_REPO_URL",
            "https://github.com/lauder0/demo-web-service-repo.git",
        )
    )
    default_branch: str = field(default_factory=lambda: _get_env("DEFAULT_BRANCH", "main"))
    default_repair_branch_prefix: str = field(
        default_factory=lambda: _get_env("DEFAULT_REPAIR_BRANCH_PREFIX", "autofix")
    )
    default_repo_root: str = field(
        default_factory=lambda: _get_env(
            "DEFAULT_REPO_ROOT",
            r"E:\projeccts\demo-web-service-repo",
        )
    )
    default_runtime_root: str = field(
        default_factory=lambda: _get_env(
            "DEFAULT_RUNTIME_ROOT",
            r"E:\projeccts\demo-web-service-runtime",
        )
    )
    default_runtime_log_path: str = field(
        default_factory=lambda: _get_env(
            "DEFAULT_RUNTIME_LOG_PATH",
            r"E:\projeccts\demo-web-service-runtime\logs\demo_service.log",
        )
    )
    default_feishu_webhook_url: str = field(default_factory=lambda: _get_env("DEFAULT_FEISHU_WEBHOOK_URL", ""))

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like compatibility helper for older code."""

        return getattr(self, key, default)


config = AppConfig()
=======
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
