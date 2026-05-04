"""Tool-result contracts exposed by AgentTool and primitive tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent_messages import ToolCall
from .run_result import ToolExecutionRecord


@dataclass(slots=True)
class AgentToolResult:
    """Structured result returned by AgentTool for parent orchestration."""

    agent_id: str
    agent_type: str
    run_id: str | None
    iteration: int | None
    summary: str
    status: str
    stop_reason: str
    turn_count: int
    allowed_tools: list[str]
    permission_mode: str
    read_only: bool
    tool_calls: list[ToolCall]
    tool_results: list[ToolExecutionRecord]
    used_tools: list[str]
    started_at: str
    finished_at: str
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    audit_record: Any | None = None
