"""Tests for the second-stage Repair Orchestrator main loop behavior."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.orchestrator import RepairOrchestrator, run
from schemas.agent_messages import AgentTurn, ToolCall
from schemas.tool_result import AgentToolResult
from tools.base import BaseTool
from errors import (
    EXECUTE_PLAN_DEVIATION,
    EXPLORE_CONTEXT_INSUFFICIENT,
    ORCH_INVALID_STAGE_JUMP,
    ORCH_INVALID_TOOL_NAME,
    ORCH_MAX_ITERATIONS_EXCEEDED,
    PLAN_INSUFFICIENT_EVIDENCE,
)


class StubMainLLMAdapter:
    def __init__(self, turns: list[AgentTurn]) -> None:
        self._turns = turns
        self.calls = 0

    def complete(self, **kwargs) -> AgentTurn:
        turn = self._turns[self.calls]
        self.calls += 1
        return turn


class FakeAgentTool(BaseTool):
    name = "agent"
    description = "Fake high-level agent tool"
    input_schema = {
        "type": "object",
        "properties": {
            "agent_type": {"type": "string"},
            "description": {"type": "string"},
            "prompt": {"type": "string"},
        },
        "required": ["agent_type", "description", "prompt"],
    }

    def __init__(self, scripted_results: dict[str, list[AgentToolResult]]) -> None:
        self._scripted_results = {key: list(value) for key, value in scripted_results.items()}
        self.calls: list[dict[str, object]] = []

    def execute(self, **kwargs) -> AgentToolResult:
        agent_type = str(kwargs["agent_type"])
        self.calls.append(dict(kwargs))
        queue = self._scripted_results.get(agent_type)
        if not queue:
            raise AssertionError(f"No scripted result left for agent_type={agent_type}")
        return queue.pop(0)

    def invoke(self, payload: dict[str, object]) -> AgentToolResult:
        self.calls.append(dict(payload))
        agent_type = str(payload["agent_tool"])
        queue = self._scripted_results.get(agent_type)
        if not queue:
            raise AssertionError(f"No scripted result left for agent_type={agent_type}")
        return queue.pop(0)


def make_agent_result(
    *,
    agent_type: str,
    summary: str,
    status: str = "completed",
    stop_reason: str = "final_response",
    error: str | None = None,
    output: dict[str, object] | None = None,
) -> AgentToolResult:
    return AgentToolResult(
        agent_id=f"{agent_type}-id",
        agent_type=agent_type,
        run_id="run-001",
        iteration=1,
        summary=summary,
        status=status,
        stop_reason=stop_reason,
        turn_count=1,
        allowed_tools=["read_code"],
        permission_mode="plan",
        read_only=True,
        tool_calls=[],
        tool_results=[],
        used_tools=[],
        started_at="2026-04-30T00:00:00+00:00",
        finished_at="2026-04-30T00:00:01+00:00",
        output=output or {},
        artifacts=[],
        errors=[],
        error=error,
        audit_record=None,
    )


def make_task_input(max_iterations: int = 3) -> dict[str, object]:
    return {
        "run_id": "run-001",
        "bug_event": {"service": "demo", "error": "ValueError"},
        "traceback": "Traceback (most recent call last): ...",
        "repo_root": "demo-repo",
        "branch": "main",
        "max_iterations": max_iterations,
    }


def make_explore_output(
    *,
    suspect_files: list[str] | None = None,
    code_snippets: list[dict[str, object]] | None = None,
    context_completeness: str = "sufficient",
) -> dict[str, object]:
    files = suspect_files or ["app.py"]
    snippets = code_snippets or [{"tool": "read_code", "content": "snippet"}]
    return {
        "repair_context": {
            "bug_summary": "Located bug in app.py",
            "traceback": "Traceback (most recent call last): ...",
            "suspect_files": files,
            "code_snippets": snippets,
            "related_tests": [],
            "recent_commits": [],
        },
        "suspect_files": files,
        "related_tests": [],
        "context_completeness": context_completeness,
    }


def make_plan_output(
    *,
    files_to_modify: list[str] | None = None,
    evidence: list[str] | None = None,
    risk_level: str = "medium",
) -> dict[str, object]:
    files = ["app.py"] if files_to_modify is None else files_to_modify
    resolved_evidence = ["Traceback points to app.py:42"] if evidence is None else evidence
    return {
        "root_cause_analysis": {
            "root_cause": "Null guard missing in app.py",
            "evidence": resolved_evidence,
            "risk_level": risk_level,
        },
        "repair_plan": {
            "root_cause": "Null guard missing in app.py",
            "fix_plan": ["Add a null guard around the failing branch"],
            "files_to_modify": files,
            "risk_level": risk_level,
        },
        "tests_to_run": ["tests/test_app.py"],
    }


def make_execute_output(*, modified_files: list[str] | None = None, need_replan: bool = False) -> dict[str, object]:
    files = modified_files or ["app.py"]
    return {
        "patch_result": {
            "modified_files": files,
            "patch_summary": ["Applied the null-guard patch"],
            "test_updates": [],
        },
        "plan_deviation": {
            "deviated": need_replan,
            "reason": "execution_did_not_produce_modifications" if need_replan else None,
        },
        "need_replan": need_replan,
    }


def make_verification_output(
    *,
    verdict: str,
    gate_status: str,
    gate_reason: str,
    ready_for_pr: bool,
    targeted_tests_passed: bool = False,
    smoke_tests_passed: bool = False,
    failed_tests: list[str] | None = None,
    failure_logs: list[str] | None = None,
    validation_successes: int = 0,
    validation_failures: int = 0,
    exploratory_only: bool = False,
    environment_only: bool = False,
    has_command_backed_evidence: bool = False,
    bug_repro_attempted: bool = False,
    bug_fix_validated: bool = False,
    regression_probe_attempted: bool = False,
    suggested_tests_attempted: bool = False,
) -> dict[str, object]:
    return {
        "verification_result": {
            "verdict": verdict,
            "targeted_tests_passed": targeted_tests_passed,
            "smoke_tests_passed": smoke_tests_passed,
            "failed_tests": failed_tests or [],
            "failure_logs": failure_logs or [],
            "environment_limitations": [],
            "successful_checks": [],
            "validation_summary": {
                "validation_commands_run": [],
                "validation_successes": validation_successes,
                "validation_failures": validation_failures,
                "exploratory_only": exploratory_only,
                "environment_only": environment_only,
                "has_command_backed_evidence": has_command_backed_evidence,
            },
            "coverage_summary": {
                "bug_repro_attempted": bug_repro_attempted,
                "bug_fix_validated": bug_fix_validated,
                "regression_probe_attempted": regression_probe_attempted,
                "suggested_tests_attempted": suggested_tests_attempted,
            },
            "gate_result": {
                "gate_status": gate_status,
                "gate_reason": gate_reason,
                "ready_for_pr": ready_for_pr,
            },
            "ready_for_pr": ready_for_pr,
        }
    }


def test_orchestrator_runs_main_thread_agent_loop_to_ready_for_pr() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="First inspect the codebase",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Now generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Fix planning", "prompt": "Create a minimal fix plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Execute the plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PASS if successful"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verification passed"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Patch the null guard in app.py",
                    output=make_plan_output(),
                )
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Patch applied successfully",
                    output=make_execute_output(),
                )
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="PASS",
                        gate_reason="verification_evidence_sufficient",
                        ready_for_pr=True,
                        targeted_tests_passed=True,
                        smoke_tests_passed=True,
                        validation_successes=1,
                        has_command_backed_evidence=True,
                        bug_repro_attempted=True,
                        bug_fix_validated=True,
                        suggested_tests_attempted=True,
                    ),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"
    assert result["current_stage"] == "READY_FOR_PR"
    assert result["iterations_used"] == 1
    assert "verify" in result["artifacts"]


def test_orchestrator_initializes_tool_context_with_detected_windows_os() -> None:
    orchestrator = RepairOrchestrator(llm_adapter=StubMainLLMAdapter([AgentTurn(kind="final", content="FAILED")]))

    state = orchestrator.initialize_run(make_task_input())

    assert state.tool_use_context.os_name in {"windows", "linux", "macos"}


def test_orchestrator_verify_fail_verdict_ends_in_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return FAIL if unsuccessful"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW: verification failed and needs another repair pass"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: FAIL",
                    output=make_verification_output(
                        verdict="FAIL",
                        gate_status="FAIL",
                        gate_reason="validation_command_failed",
                        ready_for_pr=False,
                        failed_tests=["test_bug_fix"],
                        failure_logs=["AssertionError"],
                        validation_failures=1,
                    ),
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"


def test_orchestrator_verify_partial_verdict_ends_in_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PARTIAL if incomplete"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW: verification remained partial"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PARTIAL",
                    output=make_verification_output(
                        verdict="PARTIAL",
                        gate_status="PARTIAL",
                        gate_reason="environment_limitations_only",
                        ready_for_pr=False,
                        environment_only=True,
                    ),
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"


def test_orchestrator_can_continue_after_verify_fail_and_reach_ready_for_pr() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Plan first fix",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Apply first fix",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify first attempt",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return FAIL if still broken"}),
            ),
            AgentTurn(
                kind="tool",
                content="Revise the plan using verification failures",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Revise plan", "prompt": "Revise the repair plan using the latest verification failures"}),
            ),
            AgentTurn(
                kind="tool",
                content="Apply second fix",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply refined patch", "prompt": "Apply the refined fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify second attempt",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify refined patch", "prompt": "Verify and return PASS if fixed"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verification passed after the refined fix"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="First repair plan",
                    output=make_plan_output(),
                ),
                make_agent_result(
                    agent_type="plan",
                    summary="Revised repair plan",
                    output=make_plan_output(),
                ),
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="First patch applied",
                    output=make_execute_output(),
                ),
                make_agent_result(
                    agent_type="execute",
                    summary="Refined patch applied",
                    output=make_execute_output(),
                ),
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: FAIL",
                    output=make_verification_output(
                        verdict="FAIL",
                        gate_status="FAIL",
                        gate_reason="validation_command_failed",
                        ready_for_pr=False,
                        failed_tests=["test_bug_fix"],
                        failure_logs=["AssertionError"],
                        validation_failures=1,
                    ),
                ),
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="PASS",
                        gate_reason="verification_evidence_sufficient",
                        ready_for_pr=True,
                        targeted_tests_passed=True,
                        smoke_tests_passed=True,
                    ),
                ),
            ],
        }
    )

    result = run(make_task_input(max_iterations=3), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"
    assert result["iterations_used"] == 2
    assert len([call for call in fake_agent_tool.calls if call.get("agent_tool") == "verify"]) == 2


def test_orchestrator_can_continue_after_verify_partial_and_reach_ready_for_pr() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Plan repair",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Apply patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify but report partial",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PARTIAL if coverage is incomplete"}),
            ),
            AgentTurn(
                kind="tool",
                content="Re-run verification with a narrower brief",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Reverify patch", "prompt": "Re-run only the missing verification steps and return PASS if complete"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verification is now complete"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Repair plan",
                    output=make_plan_output(),
                )
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Patch applied",
                    output=make_execute_output(),
                )
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PARTIAL",
                    output=make_verification_output(
                        verdict="PARTIAL",
                        gate_status="PARTIAL",
                        gate_reason="environment_limitations_only",
                        ready_for_pr=False,
                    ),
                ),
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="PASS",
                        gate_reason="verification_evidence_sufficient",
                        ready_for_pr=True,
                        targeted_tests_passed=True,
                        smoke_tests_passed=True,
                    ),
                ),
            ],
        }
    )

    result = run(make_task_input(max_iterations=3), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"
    assert result["iterations_used"] == 2


def test_orchestrator_verify_pass_text_but_partial_gate_ends_in_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PASS if evidence is sufficient"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verifier said pass, so finalize"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="PARTIAL",
                        gate_reason="missing_bug_path_or_regression_coverage",
                        ready_for_pr=False,
                        targeted_tests_passed=True,
                        smoke_tests_passed=True,
                        validation_successes=1,
                        has_command_backed_evidence=True,
                    ),
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"


def test_orchestrator_verify_pass_text_but_fail_gate_ends_in_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PASS if evidence is sufficient"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verifier said pass, so finalize"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="FAIL",
                        gate_reason="validation_command_failed",
                        ready_for_pr=False,
                        failed_tests=["test_bug_fix"],
                        failure_logs=["AssertionError"],
                        validation_failures=1,
                    ),
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"


def test_orchestrator_missing_verification_result_defaults_to_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify the patch"}),
            ),
            AgentTurn(kind="final", content="looks probably fine"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="Verification complete",
                    output={},
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"


def test_orchestrator_writes_formal_tool_result_observations() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ]
        }
    )
    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)
    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert len(fake_agent_tool.calls) == 1
    assert fake_agent_tool.calls[0]["run_id"] == "run-001"
    assert fake_agent_tool.calls[0]["iteration"] == 1
    assert fake_agent_tool.calls[0]["input"]["description"] == "Traceback review"
    assert fake_agent_tool.calls[0]["input"]["prompt"] == "Investigate traceback"
    assert result["artifacts"]["explore"]["output"]["repair_context"]["bug_summary"] == "Located bug in app.py"


def test_orchestrator_payload_preserves_main_thread_description_and_prompt() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Now plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan from the current evidence"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Plan drafted",
                    output=make_plan_output(),
                )
            ],
        }
    )

    run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    plan_call = fake_agent_tool.calls[1]
    assert plan_call["agent_tool"] == "plan"
    assert plan_call["input"]["description"] == "Plan repair"
    assert plan_call["input"]["prompt"] == "Create a repair plan from the current evidence"


def test_orchestrator_builds_verify_brief_with_web_service_context() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Plan next",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Execute next",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply patch"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify finally",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify the repaired route and rerun the target tests"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(suspect_files=["app.py"]),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Plan the app.py fix",
                    output=make_plan_output(files_to_modify=["app.py"]),
                )
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Patch applied",
                    output=make_execute_output(modified_files=["app.py"]),
                )
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PARTIAL",
                    output=make_verification_output(
                        verdict="PARTIAL",
                        gate_status="PARTIAL",
                        gate_reason="environment_limitations_only",
                        ready_for_pr=False,
                    ),
                )
            ],
        }
    )

    run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    verify_call = fake_agent_tool.calls[3]
    verify_prompt = str(verify_call["input"]["prompt"])
    assert "Verification brief for the repaired web service bug." in verify_prompt
    assert "error_type:" in verify_prompt
    assert "traceback_snippet:" in verify_prompt
    assert "suggested_tests_to_run:" in verify_prompt
    assert "modified_files:" in verify_prompt
    assert "Original bug path validation" in verify_prompt
    assert "Regression or boundary validation" in verify_prompt


def test_orchestrator_verify_to_plan_relies_on_main_thread_prompt_not_runtime_injection() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Verify current state",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Recheck patch", "prompt": "Re-check the patch and report failures"}),
            ),
            AgentTurn(
                kind="tool",
                content="Revise the plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Revise plan", "prompt": "Revise the repair plan using the latest failures"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: FAIL",
                    output=make_verification_output(
                        verdict="FAIL",
                        gate_status="FAIL",
                        gate_reason="validation_command_failed",
                        ready_for_pr=False,
                        failed_tests=["test_bug_fix"],
                        failure_logs=["AssertionError: expected false, got true"],
                        validation_failures=1,
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Plan revised",
                    output=make_plan_output(),
                )
            ],
        }
    )

    run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    plan_call = fake_agent_tool.calls[1]
    assert plan_call["input"]["description"] == "Revise plan"
    assert plan_call["input"]["prompt"] == "Revise the repair plan using the latest failures"


def test_orchestrator_plan_to_explore_relies_on_main_thread_prompt_not_runtime_injection() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Plan first from partial evidence",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Draft plan", "prompt": "Draft a repair plan from current evidence"}),
            ),
            AgentTurn(
                kind="tool",
                content="Explore unresolved details",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Resolve uncertainty", "prompt": "Investigate the unresolved uncertainty from planning"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    partial_plan_output = {
        "root_cause_analysis": {
            "root_cause": "Possibly null guard or missing config branch",
            "evidence": ["Two plausible branches remain"],
            "risk_level": "medium",
        },
        "repair_plan": {
            "root_cause": "Possibly null guard or missing config branch",
            "fix_plan": ["Need more evidence before editing"],
            "files_to_modify": ["app.py"],
            "risk_level": "medium",
        },
        "tests_to_run": [],
    }
    fake_agent_tool = FakeAgentTool(
        {
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Planning found unresolved ambiguity",
                    output=partial_plan_output,
                )
            ],
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Additional evidence gathered",
                    output=make_explore_output(),
                )
            ],
        }
    )

    run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    explore_call = fake_agent_tool.calls[1]
    assert explore_call["input"]["description"] == "Resolve uncertainty"
    assert explore_call["input"]["prompt"] == "Investigate the unresolved uncertainty from planning"


def test_orchestrator_escalates_when_explore_context_is_insufficient() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Investigate first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Could not locate enough evidence",
                    output=make_explore_output(
                        suspect_files=[],
                        code_snippets=[],
                        context_completeness="insufficient",
                    ),
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    # current implementation can terminate without explicit explore error code; this locks the final behavior only


def test_orchestrator_rejects_invalid_tool_name_then_escalates_on_repeat() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(kind="tool", content="Call wrong tool", tool_call=ToolCall(name="read_code", arguments={})),
            AgentTurn(kind="tool", content="Call wrong tool again", tool_call=ToolCall(name="read_code", arguments={})),
        ]
    )
    fake_agent_tool = FakeAgentTool({})

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert any(error["code"] == ORCH_INVALID_TOOL_NAME for error in result["errors"])


def test_orchestrator_escalates_when_plan_requests_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Now generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Fix planning", "prompt": "Create a minimal fix plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Evidence is insufficient",
                    output={
                        "root_cause_analysis": {
                            "root_cause": "Unknown",
                            "evidence": [],
                            "risk_level": "high",
                        },
                        "repair_plan": {
                            "root_cause": "Unknown",
                            "fix_plan": [],
                            "files_to_modify": [],
                            "risk_level": "high",
                        },
                        "tests_to_run": [],
                    },
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"


def test_orchestrator_plan_fallback_allows_continue_when_summary_matches_explore_context() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Execute the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify the patch",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return PASS if successful"}),
            ),
            AgentTurn(kind="final", content="READY_FOR_PR: verification passed"),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in calculator.py and app.py",
                    output=make_explore_output(
                        suspect_files=[
                            r"E:\projeccts\demo-web-service-repo\demo_service\calculator.py",
                            r"E:\projeccts\demo-web-service-repo\demo_service\app.py",
                        ],
                        code_snippets=[
                            {"tool": "read_code", "content": "divide_numbers in calculator.py returns a / b"},
                            {"tool": "read_code", "content": "app.py divide endpoint catches Exception and returns 500"},
                        ],
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary=(
                        "Modify E:\\projeccts\\demo-web-service-repo\\demo_service\\calculator.py "
                        "to add a zero divisor guard, and update app.py to catch ValueError and return 400."
                    ),
                    output=make_plan_output(files_to_modify=[], evidence=[]),
                )
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Patch applied successfully",
                    output=make_execute_output(),
                )
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output=make_verification_output(
                        verdict="PASS",
                        gate_status="PASS",
                        gate_reason="verification_evidence_sufficient",
                        ready_for_pr=True,
                        targeted_tests_passed=True,
                        smoke_tests_passed=True,
                        validation_successes=1,
                        has_command_backed_evidence=True,
                        bug_repro_attempted=True,
                        bug_fix_validated=True,
                        regression_probe_attempted=True,
                    ),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "READY_FOR_PR"
    assert result["artifacts"]["plan"]["fallback_used"] is True
    assert result["artifacts"]["plan"]["fallback_reason"] == "fallback_from_plan_summary_and_explore_context"
    assert result["artifacts"]["plan"]["output"]["repair_plan"]["files_to_modify"] == [
        r"E:\projeccts\demo-web-service-repo\demo_service\calculator.py",
        r"E:\projeccts\demo-web-service-repo\demo_service\app.py",
    ]
    assert result["artifacts"]["plan"]["output"]["root_cause_analysis"]["evidence"]


def test_orchestrator_plan_fallback_blocks_when_summary_files_are_outside_explore_context() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(
                        suspect_files=[r"E:\projeccts\demo-web-service-repo\demo_service\app.py"],
                        code_snippets=[{"tool": "read_code", "content": "app.py divide endpoint catches Exception and returns 500"}],
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Modify service.py to add a zero divisor guard.",
                    output=make_plan_output(files_to_modify=[], evidence=[]),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert result["artifacts"]["plan"]["fallback_used"] is True
    assert result["artifacts"]["plan"]["fallback_reason"] == "fallback_blocked_no_actionable_file_match"


def test_orchestrator_plan_fallback_blocks_when_summary_lacks_clear_action() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(
                        suspect_files=[r"E:\projeccts\demo-web-service-repo\demo_service\app.py"],
                        code_snippets=[{"tool": "read_code", "content": "app.py divide endpoint catches Exception and returns 500"}],
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="The issue likely involves app.py and may require further analysis before a final conclusion.",
                    output=make_plan_output(files_to_modify=[], evidence=[]),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert result["artifacts"]["plan"]["fallback_used"] is True
    assert result["artifacts"]["plan"]["fallback_reason"] == "fallback_blocked_summary_lacks_clear_action"


def test_orchestrator_stops_before_plan_when_explore_context_is_insufficient() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Could not locate enough evidence",
                    output=make_explore_output(
                        suspect_files=[],
                        code_snippets=[],
                        context_completeness="insufficient",
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Modify app.py to catch ValueError and return 400.",
                    output=make_plan_output(files_to_modify=[], evidence=[]),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert "plan" not in result["artifacts"]


def test_orchestrator_plan_fallback_blocks_on_high_risk_plan() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Inspect first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Generate a plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Plan repair", "prompt": "Create a repair plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(
                        suspect_files=[r"E:\projeccts\demo-web-service-repo\demo_service\app.py"],
                        code_snippets=[{"tool": "read_code", "content": "app.py divide endpoint catches Exception and returns 500"}],
                    ),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Modify app.py to catch ValueError and return 400.",
                    output=make_plan_output(files_to_modify=[], evidence=[], risk_level="high"),
                )
            ],
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert result["artifacts"]["plan"]["fallback_used"] is True
    assert result["artifacts"]["plan"]["fallback_reason"] == "fallback_blocked_high_risk_plan"


def test_orchestrator_escalates_when_execute_needs_replan() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore first",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Execute the plan",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [make_agent_result(agent_type="explore", summary="Located bug in app.py")],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Execution could not apply the patch",
                    output={
                        "patch_result": {
                            "modified_files": [],
                            "patch_summary": [],
                            "test_updates": [],
                        },
                        "plan_deviation": {
                            "deviated": True,
                            "reason": "execution_did_not_produce_modifications",
                        },
                        "need_replan": True,
                    },
                )
            ]
        }
    )

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"


def test_orchestrator_rejects_execute_as_first_action() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Jump straight to execute",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Immediate patch", "prompt": "Patch immediately"}),
            ),
            AgentTurn(kind="final", content="NEED_HUMAN_REVIEW"),
        ]
    )
    fake_agent_tool = FakeAgentTool({})

    result = run(make_task_input(), llm_adapter=main_adapter, agent_tool=fake_agent_tool)

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert any(error["code"] == ORCH_INVALID_STAGE_JUMP for error in result["errors"])


def test_orchestrator_verify_fail_after_first_iteration_ends_in_human_review() -> None:
    main_adapter = StubMainLLMAdapter(
        [
            AgentTurn(
                kind="tool",
                content="Explore again",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "explore", "description": "Traceback review", "prompt": "Investigate traceback"}),
            ),
            AgentTurn(
                kind="tool",
                content="Plan again",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Fix planning", "prompt": "Create a minimal fix plan"}),
            ),
            AgentTurn(
                kind="tool",
                content="Execute again",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "execute", "description": "Apply patch", "prompt": "Apply the planned fix"}),
            ),
            AgentTurn(
                kind="tool",
                content="Verify and still fail",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "verify", "description": "Verify patch", "prompt": "Verify and return FAIL if unsuccessful"}),
            ),
            AgentTurn(
                kind="tool",
                content="Retry from planning",
                tool_call=ToolCall(name="agent", arguments={"agent_type": "plan", "description": "Revise plan", "prompt": "Revise the fix plan"}),
            ),
        ]
    )
    fake_agent_tool = FakeAgentTool(
        {
            "explore": [
                make_agent_result(
                    agent_type="explore",
                    summary="Located bug in app.py",
                    output=make_explore_output(),
                )
            ],
            "plan": [
                make_agent_result(
                    agent_type="plan",
                    summary="Patch the null guard in app.py",
                    output=make_plan_output(),
                )
            ],
            "execute": [
                make_agent_result(
                    agent_type="execute",
                    summary="Patch applied successfully",
                    output=make_execute_output(),
                )
            ],
            "verify": [
                make_agent_result(
                    agent_type="verify",
                    summary="VERDICT: FAIL",
                    output=make_verification_output(
                        verdict="FAIL",
                        gate_status="FAIL",
                        gate_reason="validation_command_failed",
                        ready_for_pr=False,
                        failed_tests=["test_bug_fix"],
                        failure_logs=["AssertionError"],
                        validation_failures=1,
                    ),
                )
            ],
        }
    )

    result = run(
        make_task_input(max_iterations=1),
        llm_adapter=main_adapter,
        agent_tool=fake_agent_tool,
    )

    assert result["final_status"] == "NEED_HUMAN_REVIEW"
    assert "verify" in result["artifacts"]
    assert result["artifacts"]["verify"]["output"]["verification_result"]["verdict"] == "FAIL"
