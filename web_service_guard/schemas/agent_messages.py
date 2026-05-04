"""Shared message-level contracts for sub-agent interactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


MessageLike = dict[str, Any]


@dataclass(slots=True)
class ToolCall:
    """Represents a single tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class AgentTurn:
    """Represents a single response step from the model."""

    kind: Literal["tool", "final"]
    content: str
    tool_call: ToolCall | None = None
    raw: Any | None = None
