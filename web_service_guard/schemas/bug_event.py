"""Schema for normalized bug events emitted by the first phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BugEvent:
    """Normalized representation of an incident ready for repair processing."""

    event_id: str
    source: str
    service: str
    repo: str
    branch: str
    detected_at: str
    error_type: str
    error_message: str
    error_summary: str
    traceback: str
    fingerprint: str
    occurred_at: str | None = None
    primary_file: str | None = None
    primary_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def timestamp(self) -> str:
        """Legacy alias used by older pipeline code."""

        return self.detected_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "service": self.service,
            "repo": self.repo,
            "branch": self.branch,
            "detected_at": self.detected_at,
            "occurred_at": self.occurred_at,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "error_summary": self.error_summary,
            "traceback": self.traceback,
            "fingerprint": self.fingerprint,
            "primary_file": self.primary_file,
            "primary_line": self.primary_line,
            "metadata": dict(self.metadata),
        }
