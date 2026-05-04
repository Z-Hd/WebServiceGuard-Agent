"""Schema for structured outputs returned by the third-stage delivery pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DeliveryResult:
    """Structured delivery outcome for PR publication and notification."""

    run_id: str
    status: str
    gate_passed: bool
    summary: str
    repo_root: str | None = None
    repair_branch: str | None = None
    commit: dict[str, Any] = field(default_factory=dict)
    pr: dict[str, Any] = field(default_factory=dict)
    notification: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "gate_passed": self.gate_passed,
            "summary": self.summary,
            "repo_root": self.repo_root,
            "repair_branch": self.repair_branch,
            "commit": dict(self.commit),
            "pr": dict(self.pr),
            "notification": dict(self.notification),
            "artifacts": dict(self.artifacts),
            "errors": list(self.errors),
        }
