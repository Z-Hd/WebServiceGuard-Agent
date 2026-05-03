"""Fresh-briefing builders for specialized second-stage sub-agents."""

from __future__ import annotations

from typing import Any


def _format_artifact_snapshot(artifacts: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in artifacts.items():
        if key.startswith("_"):
            continue
        if not isinstance(value, dict):
            continue
        status = value.get("status", "unknown")
        summary = value.get("summary", "")
        details: list[str] = []
        output = value.get("output", {})
        if key == "explore":
            suspect_files = output.get("suspect_files", [])
            if suspect_files:
                details.append(f"suspect_files={', '.join(suspect_files[:3])}")
        elif key == "plan":
            repair_plan = output.get("repair_plan", {})
            files_to_modify = repair_plan.get("files_to_modify", [])
            if files_to_modify:
                details.append(f"files_to_modify={', '.join(files_to_modify[:3])}")
        elif key == "execute":
            modified_files = output.get("patch_result", {}).get("modified_files", [])
            if modified_files:
                details.append(f"modified_files={', '.join(modified_files[:3])}")
        elif key == "verify":
            verification = output.get("verification_result", {})
            verdict = verification.get("verdict")
            if verdict:
                details.append(f"verdict={verdict}")
            failed_tests = verification.get("failed_tests", [])
            if failed_tests:
                details.append(f"failed_tests={', '.join(failed_tests[:3])}")
        suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- {key}: status={status}; summary={summary}{suffix}")
    return "\n".join(lines) if lines else "- No previous agent results."


def _format_errors(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "- No recorded orchestrator errors."
    lines: list[str] = []
    for error in errors[-3:]:
        code = error.get("code", "UNKNOWN")
        message = error.get("message", "")
        lines.append(f"- {code}: {message}")
    return "\n".join(lines)


def _build_shared_header(
    agent_type: str,
    requested_user_prompt: str,
    orchestrator_context: dict[str, Any],
) -> str:
    transition = orchestrator_context.get("current_transition") or {}
    transition_text = (
        f"{transition.get('reason')} / source={transition.get('source')} / retryable={transition.get('retryable')}"
        if transition
        else "None"
    )
    return (
        f"You are being called as the `{agent_type}` specialized sub-agent.\n\n"
        "This is a fresh sub-agent invocation. You do not inherit hidden context from prior calls. "
        "Use the orchestrator's briefing below as the source of truth for this task.\n\n"
        "## Requested task\n"
        f"{requested_user_prompt}\n\n"
        "## Current orchestrator context\n"
        f"- run_id: {orchestrator_context.get('run_id')}\n"
        f"- repo: {orchestrator_context.get('repo')}\n"
        f"- branch: {orchestrator_context.get('branch')}\n"
        f"- turn_count: {orchestrator_context.get('turn_count')}\n"
        f"- last_agent_tool: {orchestrator_context.get('last_agent_tool')}\n"
        f"- last_agent_result_summary: {orchestrator_context.get('last_agent_result_summary')}\n"
        f"- current_transition: {transition_text}\n"
        f"- traceback: {orchestrator_context.get('traceback')}\n\n"
        "## Prior agent results\n"
        f"{_format_artifact_snapshot(orchestrator_context.get('artifacts', {}))}\n\n"
        "## Recent orchestrator errors\n"
        f"{_format_errors(orchestrator_context.get('errors', []))}\n"
    )


def build_explore_brief(
    requested_user_prompt: str,
    orchestrator_context: dict[str, Any],
    agent_inputs: dict[str, Any],
) -> str:
    return (
        _build_shared_header("explore", requested_user_prompt, orchestrator_context)
        + "\n"
        + "## Your task in this call\n"
        + "Gather or refine evidence. Focus on locating the failing code path, relevant files, likely root-cause hypotheses, "
        + "and any missing context that blocks safe planning or execution.\n"
        + "If a prior plan or verification result left open questions, investigate those open questions directly rather than restarting from zero.\n\n"
        + "## Convenience fields\n"
        + f"- service: {agent_inputs.get('service')}\n"
        + f"- entry_request: {agent_inputs.get('entry_request')}\n"
        + "## Expected output focus\n"
        + "- suspect files backed by evidence\n"
        + "- concise root-cause hypotheses\n"
        + "- any remaining unknowns that still block planning or execution\n"
    )


def build_plan_brief(
    requested_user_prompt: str,
    orchestrator_context: dict[str, Any],
    agent_inputs: dict[str, Any],
) -> str:
    return (
        _build_shared_header("plan", requested_user_prompt, orchestrator_context)
        + "\n"
        + "## Your task in this call\n"
        + "Synthesize the currently known evidence into a concrete repair strategy. "
        + "If a previous verification attempt failed, treat those failures as first-class inputs and revise the plan accordingly.\n"
        + "Do not assume exploration is complete just because an `explore` result exists; instead, plan from the full current context.\n\n"
        + "## Convenience fields\n"
        + f"- prior_repair_context: {agent_inputs.get('repair_context')}\n"
        + "## Expected output focus\n"
        + "- root cause analysis tied to evidence\n"
        + "- minimal fix plan\n"
        + "- files to modify\n"
        + "- tests or checks that should be run after implementation\n"
    )


def build_execute_brief(
    requested_user_prompt: str,
    orchestrator_context: dict[str, Any],
    agent_inputs: dict[str, Any],
) -> str:
    return (
        _build_shared_header("execute", requested_user_prompt, orchestrator_context)
        + "\n"
        + "## Your task in this call\n"
        + "Implement the safest minimal change that matches the current orchestrator understanding. "
        + "Use the current plan if available, but rely on the overall briefing rather than assuming the plan artifact is the only truth.\n"
        + "If the available context is not concrete enough to implement safely, fail clearly rather than improvising a broad refactor.\n\n"
        + "## Convenience fields\n"
        + f"- prior_repair_plan: {agent_inputs.get('repair_plan')}\n"
        + "## Expected output focus\n"
        + "- minimal patch aligned with the intended fix\n"
        + "- modified files\n"
        + "- whether any replan is needed because implementation reality differed from expectations\n"
    )


def build_verify_brief(
    requested_user_prompt: str,
    orchestrator_context: dict[str, Any],
    agent_inputs: dict[str, Any],
) -> str:
    return (
        _build_shared_header("verify", requested_user_prompt, orchestrator_context)
        + "\n"
        + "## Your task in this call\n"
        + "Validate the current implementation using command-backed evidence. "
        + "Base your verdict on actual command output and the current modified files, not on optimism or prior summaries.\n"
        + "If previous verification failed, treat those failures as regression targets and explicitly re-check them.\n\n"
        + "## Convenience fields\n"
        + f"- modified_files: {agent_inputs.get('modified_files')}\n"
        + f"- tests_to_run: {agent_inputs.get('tests_to_run')}\n"
        + f"- smoke_tests: {agent_inputs.get('smoke_tests')}\n"
        + "## Expected output focus\n"
        + "- command-backed verification evidence\n"
        + "- PASS / FAIL / PARTIAL verdict\n"
        + "- failed checks and failure logs when verification does not pass\n"
    )
