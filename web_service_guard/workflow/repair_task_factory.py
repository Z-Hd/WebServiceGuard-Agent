"""Build formal repair tasks from normalized bug events."""

from __future__ import annotations

from datetime import datetime, timezone

from web_service_guard.config import config
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.repair_task import RepairTask


class RepairTaskFactory:
    """Create formal repair tasks from normalized bug events."""

    def __init__(self, *, default_max_iterations: int | None = None) -> None:
        self._default_max_iterations = default_max_iterations or config.max_iterations

    def build(
        self,
        *,
        bug_event: BugEvent,
        repo_root: str,
        max_iterations: int | None = None,
        requested_by: str = "system",
        priority: str = "normal",
        constraints: dict | None = None,
        metadata: dict | None = None,
    ) -> RepairTask:
        created_at = _utc_now()
        return RepairTask(
            run_id=self._build_run_id(bug_event, created_at),
            bug_event=bug_event,
            repo_root=repo_root,
            max_iterations=max_iterations or self._default_max_iterations,
            priority=priority,
            requested_by=requested_by,
            created_at=created_at,
            constraints=dict(constraints or {}),
            metadata=dict(metadata or {}),
        )

    def _build_run_id(self, bug_event: BugEvent, created_at: str) -> str:
        service_slug = bug_event.service.strip().replace("/", "-").replace(" ", "-") or "service"
        fingerprint = bug_event.fingerprint[:8]
        timestamp = created_at.replace("-", "").replace(":", "").replace(".", "")
        timestamp = timestamp.replace("+0000", "Z").replace("+00:00", "Z")
        return f"repair_{service_slug}_{fingerprint}_{timestamp}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
