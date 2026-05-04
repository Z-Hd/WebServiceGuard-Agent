"""Schema for extracted traceback candidates discovered during phase one."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TracebackCandidate:
    """A candidate traceback block extracted from logs or another signal source."""

    raw_text: str
    source: str
    detected_at: str
    fingerprint: str
    service: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "source": self.source,
            "detected_at": self.detected_at,
            "fingerprint": self.fingerprint,
            "service": self.service,
            "metadata": dict(self.metadata),
        }
