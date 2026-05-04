"""Schema for first-phase incident triggers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class IncidentTrigger:
    """Represents the reason phase one started investigating a service issue."""

    source: Literal["log", "healthcheck", "manual"]
    service: str
    repo: str
    branch: str
    detected_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "service": self.service,
            "repo": self.repo,
            "branch": self.branch,
            "detected_at": self.detected_at,
            "metadata": dict(self.metadata),
        }
