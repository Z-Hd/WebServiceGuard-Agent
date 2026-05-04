"""Smoke test for real main-thread LLM orchestrator tool-calling behavior."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from runtime.orchestrator import run
from schemas.tool_result import AgentToolResult
from tools.base import BaseTool


@dataclass
class ScriptedAgentResult:
    agent_type: str
    summary: str
    output: dict[str, Any]


class InspectingFakeAgentTool(BaseTool):
    name = "agent"
    description = "Fake agent tool for real-LLM orchestrator smoke tests"
    input_schema = {
        "type": "object",
        "properties": {
            "agent_type": {"type": "string"},
            "description": {"type": "string"},
            "prompt": {"type": "string"},
        },
        "required": ["agent_type", "description", "prompt"],
    }

    def __init__(self, scripted_results: dict[str, list[ScriptedAgentResult]]) -> None:
        self.scripted_results = {k: list(v) for k, v in scripted_results.items()}
        self.calls: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any]) -> AgentToolResult:
        self.calls.append(payload)
        agent_type = str(payload["agent_tool"])
        queue = self.scripted_results.get(agent_type)
        if not queue:
            raise AssertionError(f"No scripted result left for agent_type={agent_type}")
        result = queue.pop(0)
        return AgentToolResult(
            agent_id=f"{agent_type}-id",
            agent_type=agent_type,
            run_id=str(payload["run_id"]),
            iteration=int(payload["iteration"]),
            summary=result.summary,
            status="completed",
            stop_reason="final_response",
            turn_count=1,
            allowed_tools=[],
            permission_mode="plan" if agent_type in {"explore", "plan", "verify"} else "acceptEdits",
            read_only=agent_type in {"explore", "plan", "verify"},
            tool_calls=[],
            tool_results=[],
            used_tools=[],
            started_at="",
            finished_at="",
            output=result.output,
            artifacts=[],
            errors=[],
            error=None,
            audit_record=None,
        )


def make_task_input() -> dict[str, Any]:
    return {
        "run_id": "smoke-run-001",
        "bug_event": {"service": "demo", "error": "ValueError"},
        "traceback": "Traceback (most recent call last): ValueError in app.py line 42",
        "repo": "demo-repo",
        "branch": "main",
        "max_iterations": 1,
    }


def main() -> None:
    adapter = OpenAICompatibleLLMAdapter.from_env()
    fake_agent_tool = InspectingFakeAgentTool(
        {
            "explore": [
                ScriptedAgentResult(
                    agent_type="explore",
                    summary="Located likely bug in app.py",
                    output={
                        "repair_context": {
                            "bug_summary": "Likely null handling issue in app.py",
                            "traceback": "Traceback (most recent call last): ValueError in app.py line 42",
                            "suspect_files": ["app.py"],
                            "code_snippets": [{"tool": "read", "content": "if item.value is None: raise ValueError"}],
                            "related_tests": ["tests/test_app.py"],
                            "recent_commits": [],
                        },
                        "suspect_files": ["app.py"],
                        "related_tests": ["tests/test_app.py"],
                        "context_completeness": "sufficient",
                    },
                )
            ],
            "plan": [
                ScriptedAgentResult(
                    agent_type="plan",
                    summary="Add null guard in app.py",
                    output={
                        "root_cause_analysis": {
                            "root_cause": "Null value not guarded before access",
                            "evidence": ["Traceback points to app.py:42"],
                            "risk_level": "medium",
                        },
                        "repair_plan": {
                            "root_cause": "Null value not guarded before access",
                            "fix_plan": ["Add a null guard before using item.value"],
                            "files_to_modify": ["app.py"],
                            "risk_level": "medium",
                        },
                        "tests_to_run": ["tests/test_app.py"],
                        "need_human_review": False,
                    },
                )
            ],
            "execute": [
                ScriptedAgentResult(
                    agent_type="execute",
                    summary="Applied null guard patch",
                    output={
                        "patch_result": {
                            "modified_files": ["app.py"],
                            "patch_summary": ["Added null guard before item.value access"],
                            "test_updates": [],
                        },
                        "plan_deviation": {"deviated": False, "reason": None},
                        "need_replan": False,
                    },
                )
            ],
            "verify": [
                ScriptedAgentResult(
                    agent_type="verify",
                    summary="VERDICT: PASS",
                    output={
                        "verification_result": {
                            "verdict": "PASS",
                            "targeted_tests_passed": True,
                            "smoke_tests_passed": True,
                            "failed_tests": [],
                            "failure_logs": [],
                            "ready_for_pr": True,
                        }
                    },
                )
            ],
        }
    )

    result = run(
        make_task_input(),
        llm_adapter=adapter,
        agent_tool=fake_agent_tool,
    )

    print("=== FINAL RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n=== AGENT TOOL CALLS ===")
    for idx, call in enumerate(fake_agent_tool.calls, start=1):
        print(f"\n[{idx}] agent_tool={call['agent_tool']}")
        print(json.dumps(call["input"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
