"""Prompt builders for the second-stage Repair Orchestrator."""

from __future__ import annotations

import json
from typing import Any

from schemas.agent_messages import MessageLike


def build_orchestrator_system_prompt() -> str:
    return (
        "You are the second-stage Repair Orchestrator.\n"
        "You must coordinate the repair workflow by using only the `agent` tool.\n"
        "You must not directly read code, modify code, or run tests.\n"
        "You may delegate only to the following sub-agents: explore, plan, execute, verify.\n"
        "Choose which sub-agent to call based on what information or action is needed next.\n"
        "Use structured observations from prior agent runs to decide whether to explore more, plan, execute, verify, retry, or stop.\n"
        "Before each `agent` call, absorb the current overall context and write a fresh, complete prompt for that sub-agent.\n"
        "Do not assume the next sub-agent can infer prior results unless you explicitly include them in the prompt.\n"
        "When `verify` returns a verification report with `VERDICT: FAIL` or `VERDICT: PARTIAL`, do not stop immediately.\n"
        "First absorb the full `verification_report`, then decide the next best agent action.\n"
        "Use this decision rule after verification:\n"
        "- If the verification report suggests the root-cause judgment was wrong or incomplete, call `explore`.\n"
        "- If the verification report suggests the repair approach was insufficient or missing important coverage, call `plan`.\n"
        "- If the verification report identifies a concrete patch problem or an obvious follow-up code change, call `execute`.\n"
        "- If the verification report suggests the implementation may already be correct but the validation was incomplete, inconclusive, or needs a narrower rerun, call `verify` again with a better brief.\n"
        "When `execute` reports `need_replan=True`, do not stop immediately.\n"
        "Treat the execute result as feedback and choose the next best recovery action.\n"
        "Use this decision rule after execute feedback:\n"
        "- If `execute` says the plan no longer matches the file contents or the implementation approach is insufficient, call `plan`.\n"
        "- If `execute` changed no files and the root cause may be wrong or context is missing, call `explore`.\n"
        "- If `execute` changed no files but the patch direction is still clear and only the edit needs refinement, you may call `execute` again with a narrower, more precise brief.\n"
        "- Do not stop just because one execute attempt failed to apply the patch.\n"
        "Only stop with `NEED_HUMAN_REVIEW` when you have no safe or useful next agent action, or when repair iterations are exhausted.\n"
        "Every `agent` tool call should include a short `description` and a full `prompt`.\n"
        "If the workflow is complete, produce a final response that explicitly states either READY_FOR_PR, NEED_HUMAN_REVIEW, or FAILED.\n"
        "If you emit an invalid action multiple times, the run will terminate.\n"
        "Do not call execute unless you have enough grounded context to describe a safe code change."
    )


def build_orchestrator_initial_messages(
    task_input: dict[str, Any],
    *,
    default_max_iterations: int,
) -> list[MessageLike]:
    user_content = (
        "Repair task received.\n"
        f"run_id: {task_input.get('run_id')}\n"
        f"repo_root: {task_input.get('repo_root')}\n"
        f"branch: {task_input.get('branch')}\n"
        f"max_iterations: {task_input.get('max_iterations', default_max_iterations)}\n"
        f"bug_event: {json.dumps(task_input.get('bug_event', {}), ensure_ascii=False)}\n"
        f"traceback: {task_input.get('traceback', '')}\n"
        "Goal: determine whether this repair can reach READY_FOR_PR or must end in NEED_HUMAN_REVIEW/FAILED.\n"
        "Use only the agent tool."
    )
    return [
        {"role": "system", "content": build_orchestrator_system_prompt()},
        {"role": "user", "content": user_content},
    ]


def build_orchestrator_guardrail_feedback(error_message: str) -> MessageLike:
    return {
        "role": "user",
        "content": (
            "Guardrail feedback: "
            f"{error_message} "
            "Correct the action and continue using only the `agent` tool."
        ),
    }
