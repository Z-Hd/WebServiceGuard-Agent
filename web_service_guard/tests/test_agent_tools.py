"""Tests for AgentTool contracts and minimal invocation behavior."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.registry import BUILTIN_AGENTS, AgentDefinition
from runtime.runtime_state import ToolUseContext
from runtime.tool_resolution import ToolResolutionError, resolve_agent_tools
from schemas.agent_messages import AgentTurn, ToolCall
from tools.agent_tool import AgentTool
from tools.base import BaseTool, ToolRegistry


class DummyTool(BaseTool):
    def __init__(self, name: str, response: str = "ok", should_fail: bool = False) -> None:
        self.name = name
        self.description = f"Tool {name}"
        self.input_schema = {}
        self._response = response
        self._should_fail = should_fail

    def execute(self, **kwargs) -> str:
        if self._should_fail:
            raise RuntimeError(f"{self.name} failed")
        return f"{self._response}:{kwargs}" if kwargs else self._response


class StubLLMAdapter:
    def __init__(self, turns: list[AgentTurn]) -> None:
        self._turns = turns
        self.calls = 0

    def complete(self, **kwargs) -> AgentTurn:
        turn = self._turns[self.calls]
        self.calls += 1
        return turn


def make_registry(*tools: BaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_builtin_agents_expose_expanded_contract() -> None:
    explore = BUILTIN_AGENTS["explore"]
    assert isinstance(explore, AgentDefinition)
    assert explore.tools == ["read_code", "read_log"]
    assert explore.disallowed_tools == []
    assert explore.permission_mode == "plan"
    assert explore.read_only is True
    assert explore.max_turns is None


def test_resolve_agent_tools_allows_full_pool_when_tools_omitted() -> None:
    registry = make_registry(DummyTool("read_code"), DummyTool("run_test"))
    definition = AgentDefinition(
        agent_type="all-tools",
        description="all",
        system_prompt="prompt",
        tools=None,
    )

    resolved = resolve_agent_tools(definition, registry)

    assert set(resolved.tool_names) == {"read_code", "run_test"}
    assert resolved.permission_mode == "default"
    assert resolved.read_only is True


def test_resolve_agent_tools_applies_allow_and_deny() -> None:
    registry = make_registry(
        DummyTool("read_code"),
        DummyTool("read_log"),
        DummyTool("edit_code"),
    )
    definition = AgentDefinition(
        agent_type="filtered",
        description="filtered",
        system_prompt="prompt",
        tools=["read_code", "edit_code"],
        disallowed_tools=["edit_code"],
    )

    resolved = resolve_agent_tools(definition, registry)

    assert resolved.tool_names == ["read_code"]
    assert resolved.permission_mode == "default"
    assert resolved.read_only is True


def test_resolve_agent_tools_rejects_unknown_tool() -> None:
    registry = make_registry(DummyTool("read_code"))
    definition = AgentDefinition(
        agent_type="bad",
        description="bad",
        system_prompt="prompt",
        tools=["read_code", "missing_tool"],
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "missing_tool" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for unknown tool")


def test_resolve_agent_tools_rejects_empty_tool_set_after_denylist() -> None:
    registry = make_registry(DummyTool("read_code"))
    definition = AgentDefinition(
        agent_type="empty",
        description="empty",
        system_prompt="prompt",
        tools=["read_code"],
        disallowed_tools=["read_code"],
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "empty tool set" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for empty tool set")


def test_resolve_agent_tools_honors_explicit_read_only_override() -> None:
    registry = make_registry(DummyTool("read_code"))
    definition = AgentDefinition(
        agent_type="override",
        description="override",
        system_prompt="prompt",
        tools=["read_code"],
        read_only=True,
    )

    resolved = resolve_agent_tools(definition, registry)

    assert resolved.read_only is True


def test_resolve_agent_tools_rejects_invalid_permission_mode() -> None:
    registry = make_registry(DummyTool("read_code"))
    definition = AgentDefinition(
        agent_type="invalid-mode",
        description="invalid",
        system_prompt="prompt",
        tools=["read_code"],
        permission_mode="unsupported",
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "Unsupported permission_mode" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for invalid permission mode")


def test_resolve_agent_tools_rejects_plan_mode_with_write_tools() -> None:
    registry = make_registry(DummyTool("edit_code"))
    definition = AgentDefinition(
        agent_type="plan-write",
        description="plan-write",
        system_prompt="prompt",
        tools=["edit_code"],
        permission_mode="plan",
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "permission_mode='plan'" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for plan mode with write tools")


def test_resolve_agent_tools_rejects_read_only_write_conflict() -> None:
    registry = make_registry(DummyTool("edit_code"))
    definition = AgentDefinition(
        agent_type="read-only-conflict",
        description="conflict",
        system_prompt="prompt",
        tools=["edit_code"],
        read_only=True,
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "read_only=True" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for read_only conflict")


def test_resolve_agent_tools_rejects_writable_without_write_tools() -> None:
    registry = make_registry(DummyTool("read_code"))
    definition = AgentDefinition(
        agent_type="writable-conflict",
        description="conflict",
        system_prompt="prompt",
        tools=["read_code"],
        read_only=False,
    )

    try:
        resolve_agent_tools(definition, registry)
    except ToolResolutionError as exc:
        assert "read_only=False" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected ToolResolutionError for writable conflict")


def test_agent_tool_returns_structured_result_and_summary_adapter() -> None:
    registry = make_registry(
        DummyTool("read_code", response="snippet"),
        DummyTool("read_log", response="log"),
    )
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Need to inspect code",
                tool_call=ToolCall(name="read_code", arguments={"path": "app.py"}),
            ),
            AgentTurn(kind="final", content="Root cause identified"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="explore", user_prompt="Check traceback")

    assert result.agent_type == "explore"
    assert result.status == "completed"
    assert result.stop_reason == "final_response"
    assert result.allowed_tools == ["read_code", "read_log"]
    assert result.permission_mode == "plan"
    assert result.read_only is True
    assert result.summary == "Root cause identified"
    assert result.turn_count == 2
    assert result.used_tools == ["read_code"]
    assert result.tool_calls[0].name == "read_code"
    assert result.tool_results[0].status == "completed"
    assert result.audit_record is not None
    assert result.audit_record.agent_id == result.agent_id
    adapter_text = StubLLMAdapter([AgentTurn(kind="final", content="Root cause identified")])
    tool_text = AgentTool(llm_adapter=adapter_text, tool_registry=registry)
    assert tool_text.execute_to_text(agent_type="explore", user_prompt="Check traceback") == "Root cause identified"


def test_agent_tool_records_failed_tool_execution() -> None:
    registry = make_registry(DummyTool("read_code", should_fail=True), DummyTool("read_log"))
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect code",
                tool_call=ToolCall(name="read_code", arguments={"path": "app.py"}),
            ),
            AgentTurn(kind="final", content="Cannot inspect further"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="explore", user_prompt="Check traceback")

    assert result.status == "completed"
    assert result.stop_reason == "final_response"
    assert result.tool_results[0].status == "failed"
    assert result.error is None


def test_agent_tool_propagates_context_permissions() -> None:
    registry = make_registry(DummyTool("edit_code"), DummyTool("read_code"))
    adapter = StubLLMAdapter([AgentTurn(kind="final", content="Edited")])
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)
    context = ToolUseContext()

    result = tool.execute(agent_type="execute", user_prompt="Fix bug", tool_use_context=context)

    assert result.allowed_tools == ["edit_code", "read_code"]
    assert result.permission_mode == "acceptEdits"
    assert result.read_only is False
    assert context.allowed_tools == ["edit_code", "read_code"]
    assert context.permission_mode == "acceptEdits"
    assert context.read_only is False


def test_verify_agent_tool_emits_stable_verification_result() -> None:
    registry = make_registry(DummyTool("run_test", should_fail=True), DummyTool("read_log"))
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Run verification command",
                tool_call=ToolCall(name="run_test", arguments={"path": "tests/test_bug.py"}),
            ),
            AgentTurn(kind="final", content="VERDICT: FAIL"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="verify", user_prompt="Verify the patch")

    verification = result.output["verification_result"]
    assert verification["verdict"] == "FAIL"
    assert verification["ready_for_pr"] is False
    assert verification["targeted_tests_passed"] is False
    assert verification["smoke_tests_passed"] is False
    assert verification["failed_tests"] == ["run_test"]
    assert verification["failure_logs"]
    assert "VERDICT: FAIL" in result.summary


def test_verify_agent_tool_downgrades_pass_when_failures_exist() -> None:
    registry = make_registry(DummyTool("run_test", should_fail=True), DummyTool("read_log"))
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Run verification command",
                tool_call=ToolCall(name="run_test", arguments={"path": "tests/test_bug.py"}),
            ),
            AgentTurn(kind="final", content="VERDICT: PASS"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="verify", user_prompt="Verify the patch")

    verification = result.output["verification_result"]
    assert verification["verdict"] == "FAIL"
    assert verification["ready_for_pr"] is False


def test_plan_agent_tool_emits_stable_plan_output() -> None:
    registry = make_registry(DummyTool("read_code", response="snippet"))
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect code",
                tool_call=ToolCall(name="read_code", arguments={"path": "service.py"}),
            ),
            AgentTurn(kind="final", content="Root cause is in service.py"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="plan", user_prompt="Create a repair plan")

    plan_output = result.output
    assert "root_cause_analysis" in plan_output
    assert "repair_plan" in plan_output
    assert isinstance(plan_output["repair_plan"]["files_to_modify"], list)
    assert plan_output["repair_plan"]["files_to_modify"] == ["service.py"]
    assert isinstance(plan_output["tests_to_run"], list)
    assert plan_output["need_human_review"] is False


def test_execute_agent_tool_emits_stable_execute_output() -> None:
    registry = make_registry(DummyTool("edit_code", response="patched"), DummyTool("read_code"))
    adapter = StubLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Apply patch",
                tool_call=ToolCall(name="edit_code", arguments={"path": "service.py"}),
            ),
            AgentTurn(kind="final", content="Patch applied in service.py"),
        ]
    )
    tool = AgentTool(llm_adapter=adapter, tool_registry=registry)

    result = tool.execute(agent_type="execute", user_prompt="Apply the repair plan")

    execute_output = result.output
    assert "patch_result" in execute_output
    assert execute_output["patch_result"]["modified_files"] == ["service.py"]
    assert execute_output["need_replan"] is False
    assert execute_output["plan_deviation"]["deviated"] is False
