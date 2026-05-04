"""AgentTool dispatcher that runs sub-agents through the shared engine."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.registry import get_agent_definition
from agents.registry import BUILTIN_AGENTS
from audit import AgentRunAuditRecord, record_agent_run
from errors import (
    ORCH_AGENT_FAILED,
    ORCH_AGENT_MAX_TURNS_REACHED,
    ORCH_AGENT_TOOL_EXECUTION_ERROR,
    ORCH_AGENT_TOOL_NOT_FOUND,
    TOOL_BASH_COMMAND_REJECTED,
    TOOL_BASH_TIMEOUT,
    TOOL_READ_CODE_FAILED,
    TOOL_READ_LOG_FAILED,
    TOOL_RUN_TEST_FAILED,
    make_error,
)
from prompts.agent_tool import build_agent_tool_description
from runtime.engine import LLMAdapter, run_agent
from runtime.runtime_state import ToolUseContext
from runtime.tool_resolution import ResolvedAgentTools, resolve_agent_tools
from schemas.run_result import AgentRunResult
from schemas.tool_result import AgentToolResult
from tools.base import BaseTool, ToolRegistry, global_tool_registry


class AgentTool(BaseTool):
    """Single dispatcher that runs a configured sub-agent by type."""

    name = "agent"
    description = build_agent_tool_description(BUILTIN_AGENTS.values())
    input_schema = {
        "type": "object",
        "properties": {
            "agent_type": {"type": "string"},
            "description": {"type": "string"},
            "prompt": {"type": "string"},
            "user_prompt": {"type": "string"},
            "system_prompt_override": {"type": "string"},
            "max_turns": {"type": "integer"},
        },
        "required": ["agent_type", "prompt"],
    }

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        tool_registry: ToolRegistry | None = None,
        default_max_turns: int = 6,
    ) -> None:
        self._llm_adapter = llm_adapter
        self._tool_registry = tool_registry or global_tool_registry
        self._default_max_turns = default_max_turns
        self.description = build_agent_tool_description(BUILTIN_AGENTS.values())

    def execute(
        self,
        *,
        agent_type: str,
        prompt: str | None = None,
        user_prompt: str | None = None,
        description: str | None = None,
        run_id: str | None = None,
        iteration: int | None = None,
        system_prompt_override: Optional[str] = None,
        tool_use_context: Optional[ToolUseContext] = None,
        max_turns: Optional[int] = None,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentToolResult:
        effective_prompt = prompt or user_prompt
        if not effective_prompt:
            raise ValueError("AgentTool requires a non-empty prompt.")
        definition = get_agent_definition(agent_type)
        resolved_tools = self._resolve_tools(definition)
        context = self._build_tool_use_context(resolved_tools, tool_use_context)

        result = run_agent(
            llm_adapter=self._llm_adapter,
            tools=resolved_tools.tools,
            agent_type=definition.agent_type,
            system_prompt=system_prompt_override or definition.system_prompt,
            user_prompt=effective_prompt,
            tool_use_context=context,
            max_turns=max_turns or definition.max_turns or self._default_max_turns,
            initial_messages=initial_messages,
        )
        return self._build_agent_tool_result(
            result,
            resolved_tools,
            run_id=run_id,
            iteration=iteration,
        )

    def execute_to_text(self, **kwargs: Any) -> str:
        """Compatibility wrapper for callers that only need the summary."""

        return self.execute(**kwargs).summary

    def _resolve_tools(self, definition: Any) -> ResolvedAgentTools:
        return resolve_agent_tools(definition, self._tool_registry)

    def _build_tool_use_context(
        self,
        resolved_tools: ResolvedAgentTools,
        tool_use_context: Optional[ToolUseContext],
    ) -> ToolUseContext:
        if tool_use_context is None:
            tool_use_context = ToolUseContext()
        tool_use_context.allowed_tools = list(resolved_tools.tool_names)
        tool_use_context.read_only = resolved_tools.read_only
        tool_use_context.permission_mode = resolved_tools.permission_mode
        return tool_use_context

    def _build_agent_tool_result(
        self,
        result: AgentRunResult,
        resolved_tools: ResolvedAgentTools,
        *,
        run_id: str | None,
        iteration: int | None,
    ) -> AgentToolResult:
        audit_record = record_agent_run(result)
        output = self._build_protocol_output(result, resolved_tools)
        summary = result.summary
        if (result.agent_type or "") == "verify":
            verdict = (output.get("verification_result") or {}).get("verdict")
            if isinstance(verdict, str) and verdict in {"PASS", "FAIL", "PARTIAL"}:
                summary = f"VERDICT: {verdict}"
        return AgentToolResult(
            agent_id=result.agent_id,
            agent_type=result.agent_type or "unknown",
            run_id=run_id,
            iteration=iteration,
            summary=summary,
            status=result.status,
            stop_reason=result.stop_reason,
            turn_count=result.turn_count,
            allowed_tools=list(resolved_tools.tool_names),
            permission_mode=resolved_tools.permission_mode or "default",
            read_only=resolved_tools.read_only,
            tool_calls=list(result.tool_calls),
            tool_results=list(result.tool_results),
            used_tools=list(result.used_tools),
            started_at=result.started_at,
            finished_at=result.finished_at,
            output=output,
            artifacts=self._build_artifacts(result),
            errors=self._build_errors(result),
            error=result.error,
            audit_record=audit_record,
        )

    def invoke(self, payload: dict[str, Any]) -> AgentToolResult:
        """Task-level invocation wrapper used by the orchestrator."""

        return self.execute(
            agent_type=str(payload["agent_tool"]),
            description=str(payload["input"].get("description", "")) or None,
            prompt=str(payload["input"].get("prompt") or payload["input"].get("user_prompt")),
            run_id=payload.get("run_id"),
            iteration=payload.get("iteration"),
            max_turns=payload.get("constraints", {}).get("max_turns"),
            tool_use_context=payload.get("tool_use_context"),
        )

    def _build_protocol_output(
        self,
        result: AgentRunResult,
        resolved_tools: ResolvedAgentTools,
    ) -> dict[str, Any]:
        agent_type = result.agent_type or "unknown"
        if agent_type == "explore":
            suspect_files = self._extract_candidate_files(result)
            related_tests = self._extract_related_tests(result)
            code_snippets = self._extract_code_snippets(result)
            context_completeness = "sufficient" if suspect_files and code_snippets else "insufficient"
            return {
                "repair_context": {
                    "bug_summary": result.summary,
                    "traceback": self._extract_traceback_snippet(result),
                    "suspect_files": suspect_files,
                    "code_snippets": code_snippets,
                    "related_tests": related_tests,
                    "recent_commits": [],
                },
                "suspect_files": suspect_files,
                "related_tests": related_tests,
                "context_completeness": context_completeness,
            }
        if agent_type == "plan":
            candidate_files = self._extract_candidate_files(result)
            evidence = self._extract_evidence(result)
            tests_to_run = self._extract_related_tests(result)
            need_human_review = result.status != "completed" or not candidate_files or not evidence
            repair_plan = {
                "root_cause": result.summary,
                "fix_plan": [result.summary],
                "files_to_modify": candidate_files,
                "risk_level": "medium",
            }
            return {
                "root_cause_analysis": {
                    "root_cause": result.summary,
                    "evidence": evidence,
                    "risk_level": "medium",
                },
                "repair_plan": repair_plan,
                "tests_to_run": tests_to_run,
                "need_human_review": need_human_review,
            }
        if agent_type == "execute":
            modified_files = self._extract_candidate_files(result)
            need_replan = result.status != "completed" or not modified_files
            return {
                "patch_result": {
                    "modified_files": modified_files,
                    "patch_summary": [result.summary],
                    "test_updates": [],
                },
                "plan_deviation": {
                    "deviated": need_replan,
                    "reason": "execution_did_not_produce_modifications" if need_replan else None,
                },
                "need_replan": need_replan,
            }
        if agent_type == "verify":
            verification_report = result.summary
            verification_result = self._build_verification_result(result, verification_report)
            return {
                "verification_result": verification_result,
                "verification_report": verification_report,
            }
        return {}

    def _build_artifacts(self, result: AgentRunResult) -> list[str]:
        artifacts: list[str] = []
        for record in result.tool_results:
            if record.output:
                artifacts.append(f"tool:{record.name}")
        return artifacts

    def _build_errors(self, result: AgentRunResult) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if result.error:
            errors.append(
                make_error(
                    code=self._error_code_for_result(result),
                    message=result.error,
                    retryable=result.status != "failed",
                    stage=(result.agent_type or "agent").upper(),
                    source=result.agent_type or "agent",
                )
            )
        for record in result.tool_results:
            if record.status == "failed":
                errors.append(
                    make_error(
                        code=self._tool_error_code(record.name),
                        message=record.error or f"{record.name} failed",
                        retryable=True,
                        stage=(result.agent_type or "agent").upper(),
                        source=record.name,
                    )
                )
        return errors

    def _extract_candidate_files(self, result: AgentRunResult) -> list[str]:
        files: list[str] = []
        for record in result.tool_calls:
            path = record.arguments.get("path") or record.arguments.get("file_path")
            if isinstance(path, str) and path not in files:
                files.append(path)
        return files

    def _extract_related_tests(self, result: AgentRunResult) -> list[str]:
        tests: list[str] = []
        for record in result.tool_calls:
            path = record.arguments.get("path") or record.arguments.get("file_path")
            if isinstance(path, str) and "test" in path.lower() and path not in tests:
                tests.append(path)
        return tests

    def _extract_traceback_snippet(self, result: AgentRunResult) -> str:
        if result.messages:
            first_user = next((msg for msg in result.messages if msg.get("role") == "user"), None)
            if first_user:
                return str(first_user.get("content", ""))
        return ""

    def _extract_code_snippets(self, result: AgentRunResult) -> list[dict[str, Any]]:
        snippets: list[dict[str, Any]] = []
        for record in result.tool_results:
            if record.output:
                snippets.append({"tool": record.name, "content": record.output})
        return snippets

    def _extract_evidence(self, result: AgentRunResult) -> list[str]:
        evidence = [record.output for record in result.tool_results if record.output]
        return [item for item in evidence if item]

    def _build_verification_result(
        self,
        result: AgentRunResult,
        verification_report: str,
    ) -> dict[str, Any]:
        bash_records = [record for record in result.tool_results if record.name == "bash"]
        bash_checks = self._build_bash_checks(bash_records)
        verification_assessment = self._assess_bash_verification(bash_checks)
        verdict = self._infer_verification_verdict(verification_report)
        if verdict == "PASS":
            targeted_tests_passed = True
            smoke_tests_passed = True
            ready_for_pr = True
        elif verdict == "FAIL":
            targeted_tests_passed = False
            smoke_tests_passed = False
            ready_for_pr = False
        else:
            targeted_tests_passed = False
            smoke_tests_passed = False
            ready_for_pr = False
        return {
            "verdict": verdict,
            "targeted_tests_passed": targeted_tests_passed,
            "smoke_tests_passed": smoke_tests_passed,
            "failed_tests": verification_assessment["failed_tests"],
            "failure_logs": verification_assessment["failure_logs"],
            "bash_checks": bash_checks,
            "environment_limitations": verification_assessment["environment_limitations"],
            "successful_checks": verification_assessment["successful_checks"],
            "ready_for_pr": ready_for_pr,
        }

    def _build_bash_checks(self, bash_records: list[Any]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for record in bash_records:
            payload = record.structured_output or {}
            command = payload.get("command")
            checks.append(
                {
                    "command": command,
                    "exit_code": payload.get("exit_code"),
                    "status": record.status,
                    "stdout": payload.get("stdout", ""),
                    "stderr": payload.get("stderr", ""),
                    "combined_output": payload.get("combined_output", ""),
                    "duration_sec": payload.get("duration_sec"),
                    "summary": record.summary or "",
                    "error": record.error or "",
                    "is_validation_command": self._is_validation_command(command),
                    "is_environment_failure": self._is_environment_failure(command, record.error or "", payload),
                    "is_exploratory_failure": self._is_exploratory_failure(command),
                }
            )
        return checks

    def _assess_bash_verification(self, bash_checks: list[dict[str, Any]]) -> dict[str, Any]:
        failed_tests: list[str] = []
        failure_logs: list[str] = []
        environment_limitations: list[str] = []
        successful_checks: list[str] = []
        validation_successes = 0
        validation_failures = 0

        for check in bash_checks:
            command = str(check.get("command") or "")
            status = check.get("status")
            is_validation = bool(check.get("is_validation_command"))
            is_environment_failure = bool(check.get("is_environment_failure"))
            is_exploratory_failure = bool(check.get("is_exploratory_failure"))
            combined_output = str(check.get("combined_output") or "")
            error = str(check.get("error") or "")
            failure_text = combined_output or error or command

            if status == "completed":
                if is_validation:
                    validation_successes += 1
                    successful_checks.append(command)
                continue

            if is_validation and not is_environment_failure:
                validation_failures += 1
                failed_tests.append("bash")
                if failure_text:
                    failure_logs.append(failure_text)
                continue

            if is_environment_failure:
                if failure_text:
                    environment_limitations.append(failure_text)
                continue

            if is_exploratory_failure:
                if failure_text:
                    failure_logs.append(failure_text)
                continue

            failed_tests.append("bash")
            if failure_text:
                failure_logs.append(failure_text)

        return {
            "failed_tests": failed_tests,
            "failure_logs": failure_logs,
            "environment_limitations": environment_limitations,
            "successful_checks": successful_checks,
            "targeted_tests_passed": validation_successes > 0 and validation_failures == 0,
            "smoke_tests_passed": validation_successes > 0 and validation_failures == 0,
            "validation_successes": validation_successes,
            "validation_failures": validation_failures,
        }

    def _is_validation_command(self, command: Any) -> bool:
        if not isinstance(command, str):
            return False
        lowered = command.lower().strip()
        return (
            "pytest" in lowered
            or "python -m unittest" in lowered
            or "python3 -m unittest" in lowered
            or lowered.startswith("python ")
            or lowered.startswith("python3 ")
            or "&& python " in lowered
            or "&& python3 " in lowered
        )

    def _is_exploratory_failure(self, command: Any) -> bool:
        if not isinstance(command, str):
            return False
        lowered = command.lower().strip()
        return lowered.startswith("ls") or lowered.startswith("pwd") or lowered.startswith("cat") or lowered.startswith("head") or lowered.startswith("tail") or lowered.startswith("echo")

    def _is_environment_failure(
        self,
        command: Any,
        error: str,
        payload: dict[str, Any],
    ) -> bool:
        combined = " ".join(
            part
            for part in [
                str(command or ""),
                error,
                str(payload.get("stdout") or ""),
                str(payload.get("stderr") or ""),
                str(payload.get("combined_output") or ""),
            ]
            if part
        ).lower()
        markers = (
            "outside the first-phase allowlist",
            "no module named pytest",
            "python: not found",
            "command timed out",
            "working directory does not exist",
            "working directory is not a directory",
        )
        return any(marker in combined for marker in markers)

    def _infer_verification_verdict(self, summary: str) -> str:
        match = re.search(r"VERDICT:\s*(PASS|FAIL|PARTIAL)", summary.upper())
        if match:
            return match.group(1)
        if "PASS" in summary.upper():
            return "PASS"
        if "FAIL" in summary.upper():
            return "FAIL"
        return "PARTIAL"

    def _error_code_for_result(self, result: AgentRunResult) -> str:
        if result.stop_reason == "tool_not_found":
            return ORCH_AGENT_TOOL_NOT_FOUND
        if result.stop_reason == "tool_execution_error":
            return ORCH_AGENT_TOOL_EXECUTION_ERROR
        if result.stop_reason == "max_turns_reached":
            return ORCH_AGENT_MAX_TURNS_REACHED
        return ORCH_AGENT_FAILED

    def _tool_error_code(self, tool_name: str) -> str:
        mapping = {
            "bash": TOOL_BASH_COMMAND_REJECTED,
            "read_code": TOOL_READ_CODE_FAILED,
            "read_log": TOOL_READ_LOG_FAILED,
            "run_test": TOOL_RUN_TEST_FAILED,
        }
        return mapping.get(tool_name, f"TOOL_{tool_name.upper()}_FAILED")
