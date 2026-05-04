"""Run-result contracts for sub-agent execution outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Literal

<<<<<<< HEAD
from .agent_messages import MessageLike, ToolCall
=======
from schemas.agent_messages import MessageLike, ToolCall
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28


@dataclass(slots=True)
class ToolExecutionRecord:
    """Structured record for one executed tool call."""

    name: str
    arguments: dict[str, object]
    status: Literal["completed", "failed"]
    output: str | None = None
    structured_output: dict[str, Any] | None = None
    summary: str | None = None
    error: str | None = None


@dataclass(slots=True)
class AgentRunResult:
    """Final summary returned by one sub-agent run."""

    agent_id: str
    agent_type: str | None
    summary: str
    status: Literal["completed", "failed", "max_turns_reached"]
    stop_reason: Literal[
        "final_response",
        "tool_execution_error",
        "tool_not_found",
        "max_turns_reached",
        "unexpected_turn",
    ]
    turn_count: int
    messages: list[MessageLike]
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolExecutionRecord] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str = ""
    finished_at: str = ""
