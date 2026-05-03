"""Tests for centralized second-stage prompt builders."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.orchestrator import (
    build_orchestrator_guardrail_feedback,
    build_orchestrator_initial_messages,
    build_orchestrator_system_prompt,
)
from prompts.agent_tool import build_agent_tool_description
from agents.registry import BUILTIN_AGENTS
from prompts.subagent_briefs import (
    build_execute_brief,
    build_explore_brief,
    build_plan_brief,
    build_verify_brief,
)
from prompts.subagents import (
    build_execute_system_prompt,
    build_explore_system_prompt,
    build_plan_system_prompt,
    build_verify_system_prompt,
)


def test_orchestrator_system_prompt_mentions_agent_only_coordination() -> None:
    prompt = build_orchestrator_system_prompt()

    assert "Repair Orchestrator" in prompt
    assert "using only the `agent` tool" in prompt
    assert "READY_FOR_PR" in prompt


def test_orchestrator_initial_messages_include_bug_event_and_traceback() -> None:
    messages = build_orchestrator_initial_messages(
        {
            "run_id": "run-001",
            "repo": "demo-repo",
            "branch": "main",
            "max_iterations": 3,
            "bug_event": {"service": "demo", "error": "ValueError"},
            "traceback": "Traceback: boom",
        },
        default_max_iterations=5,
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "run_id: run-001" in str(messages[1]["content"])
    assert "Traceback: boom" in str(messages[1]["content"])


def test_orchestrator_guardrail_feedback_is_user_message() -> None:
    message = build_orchestrator_guardrail_feedback("Do not call execute first.")

    assert message["role"] == "user"
    assert "Guardrail feedback:" in str(message["content"])
    assert "Do not call execute first." in str(message["content"])


def test_subagent_prompts_are_exposed_from_central_module() -> None:
    assert "Bug 探索专家" in build_explore_system_prompt()
    assert "顶级系统架构师" in build_plan_system_prompt()
    assert "代码修改机器" in build_execute_system_prompt()
    assert "安全测试门禁" in build_verify_system_prompt()


def test_agent_tool_description_explains_agent_selection_workflow() -> None:
    description = build_agent_tool_description(BUILTIN_AGENTS.values())

    assert "The `agent` tool is the only tool the main Repair Orchestrator should call directly." in description
    assert "When NOT to use the `agent` tool:" in description
    assert "## Writing the prompt" in description
    assert "## Agent selection guidance" in description
    assert "Never delegate understanding." in description
    assert "- explore:" in description
    assert "- plan:" in description
    assert "- execute:" in description
    assert "- verify:" in description
    assert "Choose the next agent based on what information is missing right now, not on a fixed sequence." in description


def test_subagent_briefs_include_goal_context_and_output_expectations() -> None:
    context = {
        "run_id": "run-001",
        "traceback": "Traceback: boom",
        "bug_event": {"service": "demo"},
        "repo": "demo-repo",
        "branch": "main",
        "turn_count": 2,
        "artifacts": {
            "explore": {
                "status": "completed",
                "summary": "Located bug in app.py",
                "output": {"suspect_files": ["app.py"]},
            },
            "verify": {
                "status": "completed",
                "summary": "VERDICT: FAIL",
                "output": {"verification_result": {"verdict": "FAIL", "failed_tests": ["test_bug_fix"]}},
            },
        },
        "last_agent_tool": "verify",
        "last_agent_result_summary": "VERDICT: FAIL",
        "current_transition": {"reason": "agent_completed", "source": "verify", "retryable": True},
        "errors": [{"code": "VERIFY_TARGETED_TEST_FAILED", "message": "Verification reported FAIL."}],
    }

    explore = build_explore_brief("Find the failing code path", context, {"service": "demo", "entry_request": {"service": "demo"}})
    plan = build_plan_brief("Revise the plan after failure", context, {"repair_context": {"suspect_files": ["app.py"]}})
    execute = build_execute_brief("Apply the minimal fix", context, {"repair_plan": {"files_to_modify": ["app.py"]}})
    verify = build_verify_brief("Re-run validation", context, {"modified_files": ["app.py"], "tests_to_run": ["tests/test_app.py"], "smoke_tests": []})

    for brief in (explore, plan, execute, verify):
        assert "## Requested task" in brief
        assert "## Current orchestrator context" in brief
        assert "## Prior agent results" in brief
        assert "## Expected output focus" in brief

    assert "If a previous verification attempt failed" in plan
    assert "Base your verdict on actual command output" in verify
