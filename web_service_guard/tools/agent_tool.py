"""AgentTool dispatcher that runs sub-agents through the shared engine."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.registry import get_agent_definition
<<<<<<< HEAD
=======
from agents.registry import BUILTIN_AGENTS
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
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
<<<<<<< HEAD
=======
from prompts.agent_tool import build_agent_tool_description
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
from runtime.engine import LLMAdapter, run_agent
from runtime.runtime_state import ToolUseContext
from runtime.tool_resolution import ResolvedAgentTools, resolve_agent_tools
from schemas.run_result import AgentRunResult
from schemas.tool_result import AgentToolResult
from tools.base import BaseTool, ToolRegistry, global_tool_registry


class AgentTool(BaseTool):
    """Single dispatcher that runs a configured sub-agent by type."""

    name = "agent"
<<<<<<< HEAD
    description = "Dispatch a sub-agent using the shared AgentEngine."
=======
    description = build_agent_tool_description(BUILTIN_AGENTS.values())
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
    input_schema = {
        "type": "object",
        "properties": {
            "agent_type": {"type": "string"},
            "user_prompt": {"type": "string"},
            "system_prompt_override": {"type": "string"},
            "max_turns": {"type": "integer"},
        },
        "required": ["agent_type", "user_prompt"],
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
<<<<<<< HEAD
=======
        self.description = build_agent_tool_description(BUILTIN_AGENTS.values())
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28

    def execute(
        self,
        *,
        agent_type: str,
        user_prompt: str,
        run_id: str | None = None,
        iteration: int | None = None,
        system_prompt_override: Optional[str] = None,
        tool_use_context: Optional[ToolUseContext] = None,
        max_turns: Optional[int] = None,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentToolResult:
        definition = get_agent_definition(agent_type)
        resolved_tools = self._resolve_tools(definition)
        context = self._build_tool_use_context(resolved_tools, tool_use_context)

        result = run_agent(
            llm_adapter=self._llm_adapter,
            tools=resolved_tools.tools,
            agent_type=definition.agent_type,
            system_prompt=system_prompt_override or definition.system_prompt,
            user_prompt=user_prompt,
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
        return AgentToolResult(
            agent_id=result.agent_id,
            agent_type=result.agent_type or "unknown",
            run_id=run_id,
            iteration=iteration,
            summary=result.summary,
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
            output=self._build_protocol_output(result, resolved_tools),
            artifacts=self._build_artifacts(result),
            errors=self._build_errors(result),
            error=result.error,
            audit_record=audit_record,
        )

    def invoke(self, payload: dict[str, Any]) -> AgentToolResult:
        """Task-level invocation wrapper used by the orchestrator."""

        return self.execute(
            agent_type=str(payload["agent_tool"]),
            user_prompt=str(payload["input"]["user_prompt"]),
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
            verification_result = self._build_verification_result(result)
            return {
                "verification_result": verification_result
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

    def _build_verification_result(self, result: AgentRunResult) -> dict[str, Any]:
        failed_tests = [record.name for record in result.tool_results if record.status == "failed"]
        failure_logs = [record.error or "" for record in result.tool_results if record.status == "failed"]
        bash_records = [record for record in result.tool_results if record.name == "bash"]
        bash_checks = self._build_bash_checks(bash_records)
        failure_logs.extend(
            check["combined_output"]
            for check in bash_checks
            if check["status"] == "failed" and check["combined_output"]
        )

        verdict = self._infer_verification_verdict_from_tools(result.summary, bash_checks, failed_tests)
        targeted_tests_passed = bool(bash_checks) and all(check["status"] == "completed" for check in bash_checks)
        smoke_tests_passed = targeted_tests_passed
        if not bash_checks:
            targeted_tests_passed = verdict == "PASS"
            smoke_tests_passed = verdict == "PASS"
        ready_for_pr = verdict == "PASS" and targeted_tests_passed and smoke_tests_passed
        return {
            "verdict": verdict,
            "targeted_tests_passed": targeted_tests_passed,
            "smoke_tests_passed": smoke_tests_passed,
            "failed_tests": failed_tests,
            "failure_logs": failure_logs,
            "bash_checks": bash_checks,
            "ready_for_pr": ready_for_pr,
        }

    def _build_bash_checks(self, bash_records: list[Any]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for record in bash_records:
            payload = record.structured_output or {}
            checks.append(
                {
                    "command": payload.get("command"),
                    "exit_code": payload.get("exit_code"),
                    "status": record.status,
                    "stdout": payload.get("stdout", ""),
                    "stderr": payload.get("stderr", ""),
                    "combined_output": payload.get("combined_output", ""),
                    "duration_sec": payload.get("duration_sec"),
                }
            )
        return checks

    def _infer_verification_verdict_from_tools(
        self,
        summary: str,
        bash_checks: list[dict[str, Any]],
        failed_tests: list[str],
    ) -> str:
        if bash_checks:
            if any(check["status"] == "failed" or check["exit_code"] not in {0, None} for check in bash_checks):
                return "FAIL"
            if failed_tests:
                return "FAIL"
            return "PASS"

        verdict = self._infer_verification_verdict(summary)
        if verdict == "PASS" and failed_tests:
            return "FAIL"
        return verdict

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
