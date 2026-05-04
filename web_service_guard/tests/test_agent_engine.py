"""Tests for AgentEngine structured results and lifecycle behavior."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.engine import run_agent
from runtime.runtime_state import ToolUseContext
from runtime.subagent_loop import run_subagent_loop
from schemas.agent_messages import AgentTurn, ToolCall
from tools.EditCodeTool import EditCodeTool
from tools.FileReadTool import FileReadTool
from tools.base import BaseTool


class DummyTool(BaseTool):
    def __init__(self, name: str, response: str = "ok", should_fail: bool = False) -> None:
        self.name = name
        self.description = name
        self.input_schema = {}
        self._response = response
        self._should_fail = should_fail

    def execute(self, **kwargs) -> str:
        if self._should_fail:
            raise RuntimeError("boom")
        return self._response


class StubLLMAdapter:
    def __init__(self, turns: list[AgentTurn]) -> None:
        self._turns = turns
        self.calls = 0

    def complete(self, **kwargs) -> AgentTurn:
        turn = self._turns[self.calls]
        self.calls += 1
        return turn


def test_run_agent_completes_after_tool_then_final() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="read_code", arguments={"path": "app.py"}),
                ),
                AgentTurn(kind="final", content="Done"),
            ]
        ),
        tools=[DummyTool("read_code", response="code")],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
    )

    assert result.status == "completed"
    assert result.stop_reason == "final_response"
    assert result.turn_count == 2
    assert result.used_tools == ["read_code"]
    assert result.tool_results[0].output == "code"
    assert result.started_at
    assert result.finished_at


def test_run_agent_preserves_structured_tool_output() -> None:
    class StructuredTool(BaseTool):
        name = "bash"
        description = "bash"
        input_schema = {}

        def execute(self, **kwargs) -> str:
            raise AssertionError("execute should not be called when structured execution is available")

        def execute_structured(self, **kwargs) -> dict[str, object]:
            return {
                "status": "completed",
                "summary": "Command completed successfully: pwd",
                "output": {
                    "command": "pwd",
                    "exit_code": 0,
                    "stdout": "/tmp\n",
                    "stderr": "",
                    "combined_output": "/tmp",
                    "duration_sec": 0.01,
                },
                "errors": [],
            }

        def format_structured_result(self, result: dict[str, object]) -> str:
            output = result["output"]
            return f"Command: {output['command']}\nExit code: {output['exit_code']}"

    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Run tool",
                    tool_call=ToolCall(name="bash", arguments={"command": "pwd"}),
                ),
                AgentTurn(kind="final", content="Done"),
            ]
        ),
        tools=[StructuredTool()],
        agent_type="verify",
        system_prompt="prompt",
        user_prompt="user",
    )

    assert result.tool_results[0].status == "completed"
    assert result.tool_results[0].output.startswith("Command: pwd")
    assert result.tool_results[0].structured_output is not None
    assert result.tool_results[0].structured_output["exit_code"] == 0


def test_run_agent_fails_on_missing_tool() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="missing", arguments={}),
                )
            ]
        ),
        tools=[],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
    )

    assert result.status == "failed"
    assert result.stop_reason == "tool_not_found"
    assert result.error is not None


def test_run_agent_fails_on_tool_execution_error() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="read_code", arguments={}),
                ),
                AgentTurn(kind="final", content="Recovered after tool error"),
            ]
        ),
        tools=[DummyTool("read_code", should_fail=True)],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
    )

    assert result.status == "completed"
    assert result.stop_reason == "final_response"
    assert result.tool_results[0].status == "failed"
    assert any(
        message.get("tool_result", {}).get("is_error") is True
        and str(message.get("content", "")).startswith("ERROR:")
        for message in result.messages
        if message.get("role") == "tool"
    )


def test_run_agent_emits_formal_tool_result_message() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="read_code", arguments={"path": "app.py"}),
                ),
                AgentTurn(kind="final", content="Done"),
            ]
        ),
        tools=[DummyTool("read_code", response="code")],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
    )

    tool_messages = [message for message in result.messages if message.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_result"]["type"] == "tool_result"
    assert tool_messages[0]["tool_result"]["tool_name"] == "read_code"
    assert tool_messages[0]["tool_result"]["is_error"] is False


def test_run_subagent_loop_continues_after_tool_execution_error() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="read_code", arguments={}),
                )
                ,
                AgentTurn(kind="final", content="Recovered after error"),
            ]
        ),
        tools=[DummyTool("read_code", should_fail=True)],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
    )

    assert result.status == "completed"
    assert result.summary == "Recovered after error"
    assert result.tool_results[0].status == "failed"


def test_run_subagent_loop_returns_missing_tool_failure() -> None:
    result = run_subagent_loop(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="missing", arguments={}),
                )
            ]
        ),
        tools=[],
        system_prompt="prompt",
        initial_messages=[],
    )

    assert result.status == "failed"
    assert result.stop_reason == "tool_not_found"


def test_run_agent_marks_max_turns_reached() -> None:
    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Use tool",
                    tool_call=ToolCall(name="read_code", arguments={}),
                )
            ]
        ),
        tools=[DummyTool("read_code")],
        agent_type="explore",
        system_prompt="prompt",
        user_prompt="user",
        max_turns=1,
    )

    assert result.status == "max_turns_reached"
    assert result.stop_reason == "max_turns_reached"


def test_run_agent_shares_tool_use_context_between_read_and_edit(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello world\n", encoding="utf-8")
    context = ToolUseContext()

    result = run_agent(
        llm_adapter=StubLLMAdapter(
            [
                AgentTurn(
                    kind="tool",
                    content="Read the file first",
                    tool_call=ToolCall(
                        name="read",
                        arguments={"file_path": str(file_path), "offset": 1, "limit": 20},
                    ),
                ),
                AgentTurn(
                    kind="tool",
                    content="Apply the edit",
                    tool_call=ToolCall(
                        name="edit",
                        arguments={
                            "file_path": str(file_path),
                            "old_string": "world",
                            "new_string": "agent",
                        },
                    ),
                ),
                AgentTurn(kind="final", content="Done"),
            ]
        ),
        tools=[FileReadTool(), EditCodeTool()],
        agent_type="execute",
        system_prompt="prompt",
        user_prompt="user",
        tool_use_context=context,
    )

    assert result.status == "completed"
    assert result.tool_results[0].status == "completed"
    assert result.tool_results[1].status == "completed"
    assert file_path.read_text(encoding="utf-8") == "hello agent\n"
