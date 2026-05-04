"""Schema for repair tasks emitted by phase one and consumed by later phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from web_service_guard.schemas.bug_event import BugEvent


@dataclass(slots=True)
class RepairTask:
    """Formal repair task created from a normalized bug event."""

    run_id: str
    bug_event: BugEvent
    repo_root: str
    max_iterations: int = 3
    priority: str = "normal"
    requested_by: str = "system"
    created_at: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "bug_event": self.bug_event.to_dict(),
            "repo_root": self.repo_root,
            "max_iterations": self.max_iterations,
            "priority": self.priority,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "constraints": dict(self.constraints),
            "metadata": dict(self.metadata),
        }
