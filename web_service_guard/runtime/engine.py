"""Sub-agent execution engine used by AgentTool dispatchers.

This module provides a minimal, dependency-injected engine that runs
an isolated sub-agent loop. It purposely does not import any AgentTool
or registry modules to avoid circular dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional, Protocol
from uuid import uuid4

from schemas.agent_messages import AgentTurn, MessageLike
from schemas.run_result import AgentRunResult
from runtime.subagent_loop import run_subagent_loop
from tools.base import BaseTool
from runtime.runtime_state import ToolUseContext


class LLMAdapter(Protocol):
    """Adapter interface for LLM inference used by the engine."""

    def complete(
        self,
        *,
        messages: List[MessageLike],
        tools: List[BaseTool],
        system_prompt: str,
        tool_use_context: Optional[ToolUseContext] = None,
    ) -> AgentTurn:
        """Return a single model turn based on the given context."""


class AgentEngine:
    """Minimal sub-agent runner that executes tool calls in a loop."""

    def __init__(self, *, llm_adapter: LLMAdapter, tools: Iterable[BaseTool], max_turns: int = 6):
        self._llm_adapter = llm_adapter
        self._tools_by_name = {tool.name: tool for tool in tools}
        self._max_turns = max_turns

    def run(
        self,
        *,
        agent_type: str | None,
        system_prompt: str,
        user_prompt: str,
        tool_use_context: Optional[ToolUseContext] = None,
        initial_messages: Optional[List[MessageLike]] = None,
    ) -> AgentRunResult:
        """Run the sub-agent loop and return the final summary."""

        started_at = _utc_now()
        agent_id = str(uuid4())
        messages: List[MessageLike] = list(initial_messages or [])
        messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        loop_result = run_subagent_loop(
            llm_adapter=self._llm_adapter,
            tools=self._tools_by_name.values(),
            system_prompt=system_prompt,
            tool_use_context=tool_use_context,
            initial_messages=messages,
            max_turns=self._max_turns,
        )
        return AgentRunResult(
            agent_id=agent_id,
            agent_type=agent_type,
            summary=loop_result.summary,
            status=loop_result.status,
            stop_reason=loop_result.stop_reason,
            turn_count=loop_result.turn_count,
            messages=loop_result.messages,
            tool_calls=loop_result.tool_calls,
            tool_results=loop_result.tool_results,
            used_tools=loop_result.used_tools,
            error=loop_result.error,
            started_at=started_at,
            finished_at=_utc_now(),
        )


def run_agent(
    *,
    llm_adapter: LLMAdapter,
    tools: Iterable[BaseTool],
    agent_type: str | None,
    system_prompt: str,
    user_prompt: str,
    tool_use_context: Optional[ToolUseContext] = None,
    max_turns: int = 6,
    initial_messages: Optional[List[MessageLike]] = None,
) -> AgentRunResult:
    """Functional wrapper mirroring Claude Code's runAgent pattern."""

    engine = AgentEngine(llm_adapter=llm_adapter, tools=tools, max_turns=max_turns)
    return engine.run(
        agent_type=agent_type,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_use_context=tool_use_context,
        initial_messages=initial_messages,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
