"""Runtime state container and helper structures for the repair loop.

This module defines the in-memory state used by the second-stage
``Repair Orchestrator`` loop. The goal is to keep a single authoritative
runtime container for:

- message history that supports agent-style reasoning
- task binding information for the current repair run
- tool-use context and permission hints
- loop control data such as turn count and completion flags
- the latest tool/agent result and accumulated errors
- references to audit events produced during execution

The state intentionally focuses on runtime orchestration concerns.
It does not implement policy decisions, tool execution, or business
workflow routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas.agent_messages import MessageLike

ErrorLike = dict[str, Any]
AgentResultLike = Any


@dataclass(slots=True)
class ToolUseContext:
    """Execution context that constrains how tools may be invoked.

    This object is inspired by Claude Code's tool-use context idea. It carries
    only the information the orchestrator and delegated tools need at runtime.
    """

    allowed_tools: list[str] = field(default_factory=list)
    read_only: bool = True
    repo_root: str | None = None
    permission_mode: str | None = None
    read_files: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class TransitionMeta:
    """Metadata describing why the loop continued, retried, or stopped."""

    reason: str
    source: str | None = None
    retryable: bool = False


@dataclass(slots=True)
class RepairRuntimeState:
    """Single runtime state container for the second-stage repair loop.

    The orchestrator should treat this object as the primary in-memory source
    of truth during execution. It keeps both the message-oriented context used
    for agentic reasoning and the loop-level control data used for audit and
    stop conditions.
    """

    # Message layer
    messages: list[MessageLike] = field(default_factory=list)

    # Task binding layer
    run_id: str = ""
    bug_event: dict[str, Any] | None = None
    traceback: str | None = None
    repo: str | None = None
    branch: str | None = None

    # Tool and permission context
    tool_use_context: ToolUseContext = field(default_factory=ToolUseContext)

    # Loop control
    turn_count: int = 0
    max_turns: int = 3
    transition: TransitionMeta | None = None
    stop_hook_active: bool = False
    done: bool = False

    # Latest execution data
    last_agent_tool: str | None = None
    last_agent_result: AgentResultLike | None = None

    # Final outcome
    final_status: str | None = None
    current_stage: str | None = None
    exit_reason: str | None = None
    ready_for_pr: bool = False
    need_human_review: bool = False
    artifacts: dict[str, Any] = field(default_factory=dict)

    # Error and audit references
    errors: list[ErrorLike] = field(default_factory=list)
    audit_event_ids: list[str] = field(default_factory=list)

    def add_message(self, message: MessageLike) -> None:
        """Append a single message-like payload to the runtime history."""

        self.messages.append(message)

    def record_agent_result(
        self,
        *,
        agent_tool: str,
        result: AgentResultLike,
        transition_reason: str | None = None,
        transition_source: str | None = None,
        retryable: bool = False,
    ) -> None:
        """Store the latest AgentTool result and optional transition metadata."""

        self.last_agent_tool = agent_tool
        self.last_agent_result = result
        if transition_reason is not None:
            self.transition = TransitionMeta(
                reason=transition_reason,
                source=transition_source,
                retryable=retryable,
            )

    def record_error(self, error: ErrorLike) -> None:
        """Append a structured error object to the runtime error list."""

        self.errors.append(error)

    def add_audit_event_id(self, audit_event_id: str) -> None:
        """Track the identifier of an audit event emitted during execution."""

        self.audit_event_ids.append(audit_event_id)

    def increment_turn(self) -> int:
        """Advance the loop turn counter and return the updated value."""

        self.turn_count += 1
        return self.turn_count

    def mark_done(
        self,
        *,
        final_status: str,
        exit_reason: str,
        ready_for_pr: bool = False,
        need_human_review: bool = False,
    ) -> None:
        """Finalize the runtime state with a terminal outcome."""

        self.done = True
        self.final_status = final_status
        self.current_stage = final_status
        self.exit_reason = exit_reason
        self.ready_for_pr = ready_for_pr
        self.need_human_review = need_human_review
