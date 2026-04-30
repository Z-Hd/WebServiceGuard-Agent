"""Structured audit event recording and query helpers for repair execution traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AgentRunLike(Protocol):
    """Minimal protocol for recording sub-agent lifecycle outcomes."""

    agent_id: str
    agent_type: str | None
    status: str
    stop_reason: str
    turn_count: int
    used_tools: list[str]
    started_at: str
    finished_at: str
    error: str | None


@dataclass(slots=True)
class AgentRunAuditRecord:
    """Minimal in-memory audit record for one sub-agent run."""

    agent_id: str
    agent_type: str | None
    status: str
    stop_reason: str
    turn_count: int
    used_tools: list[str]
    started_at: str
    finished_at: str
    error: str | None = None


def record_agent_run(result: AgentRunLike) -> AgentRunAuditRecord:
    """Create a minimal audit record for a completed sub-agent run."""

    return AgentRunAuditRecord(
        agent_id=result.agent_id,
        agent_type=result.agent_type,
        status=result.status,
        stop_reason=result.stop_reason,
        turn_count=result.turn_count,
        used_tools=list(result.used_tools),
        started_at=result.started_at,
        finished_at=result.finished_at,
        error=result.error,
    )
