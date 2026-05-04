"""Lightweight query-loop layer for a single sub-agent session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Protocol

from runtime.runtime_state import ToolUseContext
from schemas.agent_messages import AgentTurn, MessageLike, ToolCall
from schemas.run_result import ToolExecutionRecord
from tools.base import BaseTool


@dataclass(slots=True)
class SubagentLoopState:
    """Mutable state for a single sub-agent loop execution."""

    messages: list[MessageLike]
    turn_count: int = 0
    max_turns: int = 6
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolExecutionRecord] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    done: bool = False
    final_summary: str = ""
    final_status: Literal["completed", "failed", "max_turns_reached"] = "completed"
    stop_reason: Literal[
        "final_response",
        "tool_execution_error",
        "tool_not_found",
        "max_turns_reached",
        "unexpected_turn",
    ] = "final_response"
    error: str | None = None


@dataclass(slots=True)
class SubagentLoopResult:
    """Structured result for the internal sub-agent loop."""

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
    tool_calls: list[ToolCall]
    tool_results: list[ToolExecutionRecord]
    used_tools: list[str]
    error: str | None = None


class LLMAdapterLike(Protocol):
    """Protocol shared with the engine's adapter abstraction."""

    def complete(
        self,
        *,
        messages: list[MessageLike],
        tools: list[BaseTool],
        system_prompt: str,
        tool_use_context: ToolUseContext | None = None,
    ) -> AgentTurn:
        """Return the next model turn for the sub-agent."""


def run_subagent_loop(
    *,
    llm_adapter: LLMAdapterLike,
    tools: Iterable[BaseTool],
    system_prompt: str,
    tool_use_context: ToolUseContext | None = None,
    initial_messages: list[MessageLike] | None = None,
    max_turns: int = 6,
) -> SubagentLoopResult:
    """Execute the internal sub-agent loop until completion or terminal stop."""

    tools_by_name = {tool.name: tool for tool in tools}
    state = SubagentLoopState(messages=list(initial_messages or []), max_turns=max_turns)

    for turn_count in range(1, max_turns + 1):
        state.turn_count = turn_count
        turn = llm_adapter.complete(
            messages=state.messages,
            tools=list(tools_by_name.values()),
            system_prompt=system_prompt,
            tool_use_context=tool_use_context,
        )

        if turn.kind == "final":
            state.messages.append({"role": "assistant", "content": turn.content})
            state.done = True
            state.final_summary = turn.content
            state.final_status = "completed"
            state.stop_reason = "final_response"
            return _to_result(state)

        if turn.kind == "tool" and turn.tool_call:
            state.tool_calls.append(turn.tool_call)
            state.messages.append({"role": "assistant", "content": turn.content})
            tool = tools_by_name.get(turn.tool_call.name)
            if tool is None:
                error = f"Tool not found: {turn.tool_call.name}"
                state.tool_results.append(
                    ToolExecutionRecord(
                        name=turn.tool_call.name,
                        arguments=turn.tool_call.arguments,
                        status="failed",
                        error=error,
                    )
                )
                state.done = True
                state.final_summary = error
                state.final_status = "failed"
                state.stop_reason = "tool_not_found"
                state.error = error
                return _to_result(state)

            try:
                tool_output, structured_result = _execute_tool(
                    tool,
                    turn.tool_call.arguments,
                    tool_use_context=tool_use_context,
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                error = f"Tool {turn.tool_call.name} execution failed: {exc}"
                state.tool_results.append(
                    ToolExecutionRecord(
                        name=turn.tool_call.name,
                        arguments=turn.tool_call.arguments,
                        status="failed",
                        error=error,
                    )
                )
                state.messages.append(
                    _build_tool_result_message(
                        tool_name=turn.tool_call.name,
                        content=f"ERROR: {error}",
                        arguments=turn.tool_call.arguments,
                        is_error=True,
                    )
                )
                continue

            status = str(structured_result.get("status", "completed"))
            summary = str(structured_result.get("summary", "")) or None
            state.used_tools.append(turn.tool_call.name)
            state.tool_results.append(
                ToolExecutionRecord(
                    name=turn.tool_call.name,
                    arguments=turn.tool_call.arguments,
                    status=status,
                    output=tool_output,
                    structured_output=structured_result.get("output"),
                    summary=summary,
                    error=summary if status == "failed" else None,
                )
            )
            state.messages.append(
                _build_tool_result_message(
                    tool_name=turn.tool_call.name,
                    content=tool_output,
                    arguments=turn.tool_call.arguments,
                    is_error=status == "failed",
                )
            )
            continue

        error = "Unexpected agent turn received from LLM adapter."
        state.done = True
        state.final_summary = error
        state.final_status = "failed"
        state.stop_reason = "unexpected_turn"
        state.error = error
        return _to_result(state)

    state.messages.append(
        {
            "role": "assistant",
            "content": "Max turns reached without a final response.",
        }
    )
    state.done = True
    state.final_summary = "Max turns reached without a final response."
    state.final_status = "max_turns_reached"
    state.stop_reason = "max_turns_reached"
    return _to_result(state)


def _to_result(state: SubagentLoopState) -> SubagentLoopResult:
    return SubagentLoopResult(
        summary=state.final_summary,
        status=state.final_status,
        stop_reason=state.stop_reason,
        turn_count=state.turn_count,
        messages=state.messages,
        tool_calls=state.tool_calls,
        tool_results=state.tool_results,
        used_tools=state.used_tools,
        error=state.error,
    )


def _build_tool_result_message(
    *,
    tool_name: str,
    content: str,
    arguments: dict[str, object],
    is_error: bool,
) -> MessageLike:
    return {
        "role": "tool",
        "name": tool_name,
        "content": content,
        "tool_result": {
            "type": "tool_result",
            "tool_name": tool_name,
            "arguments": arguments,
            "content": content,
            "is_error": is_error,
        },
    }


def _execute_tool(
    tool: BaseTool,
    arguments: dict[str, object],
    *,
    tool_use_context: ToolUseContext | None = None,
) -> tuple[str, dict[str, object]]:
    merged_arguments = dict(arguments)
    if tool_use_context is not None and "tool_use_context" not in merged_arguments:
        merged_arguments["tool_use_context"] = tool_use_context

    execute_structured = getattr(tool, "execute_structured", None)
    supports_structured = tool.__class__.execute_structured is not BaseTool.execute_structured
    if callable(execute_structured) and supports_structured:
        structured_result = execute_structured(**merged_arguments)
        format_result = getattr(tool, "format_structured_result", None)
        if callable(format_result):
            text_output = format_result(structured_result)
        else:
            summary = str(structured_result.get("summary", ""))
            if structured_result.get("status") == "failed":
                text_output = f"ERROR: {summary}" if summary else "ERROR"
            else:
                text_output = summary
        return text_output, structured_result

    text_output = tool.execute(**merged_arguments)
    status = "failed" if text_output.startswith("ERROR:") else "completed"
    summary = text_output.removeprefix("ERROR: ").strip() if status == "failed" else text_output
    return text_output, {
        "status": status,
        "summary": summary,
        "output": None,
        "errors": [],
    }
