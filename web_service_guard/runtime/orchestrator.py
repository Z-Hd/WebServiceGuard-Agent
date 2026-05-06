"""Main Repair Orchestrator entry point that owns the second-stage repair loop."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from typing import Any

from agents.registry import get_agent_definition
from errors import (
    EXECUTE_PLAN_DEVIATION,
    EXECUTE_PATCH_APPLY_FAILED,
    EXPLORE_CONTEXT_INSUFFICIENT,
    ORCH_AGENT_TOOL_ERROR,
    ORCH_INVALID_AGENT_TYPE,
    ORCH_INVALID_MAIN_TURN,
    ORCH_INVALID_STAGE_JUMP,
    ORCH_INVALID_TOOL_NAME,
    ORCH_MAX_ITERATIONS_EXCEEDED,
    ORCH_MAX_MAIN_TURNS_REACHED,
    ORCH_MISSING_AGENT_TYPE,
    ORCH_MISSING_USER_PROMPT,
    PLAN_INSUFFICIENT_EVIDENCE,
    PLAN_UNACTIONABLE_REPAIR_PLAN,
    make_error,
)
from prompts.orchestrator import (
    build_orchestrator_guardrail_feedback,
    build_orchestrator_initial_messages,
    build_orchestrator_system_prompt,
)
from runtime.engine import LLMAdapter
from runtime.runtime_state import RepairRuntimeState, ToolUseContext
from schemas.agent_messages import AgentTurn, MessageLike, ToolCall
from schemas.tool_result import AgentToolResult
from tools.agent_tool import AgentTool
from tools.base import BaseTool, ToolRegistry, global_tool_registry


@dataclass(slots=True)
class PlanFallbackDecision:
    """Fallback decision for incomplete plan outputs."""

    used: bool
    allow_continue: bool
    reason: str
    files_to_modify: list[str]
    evidence: list[str]


class RepairOrchestrator:
    """Main-thread LLM orchestrator for the second-stage repair workflow."""

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        agent_tool: BaseTool | None = None,
        subagent_llm_adapter: LLMAdapter | None = None,
        tool_registry: ToolRegistry | None = None,
        default_max_iterations: int = 3,
        default_agent_max_turns: int = 6,
    ) -> None:
        self._llm_adapter = llm_adapter
        self._tool_registry = tool_registry or global_tool_registry
        self._default_max_iterations = default_max_iterations
        self._default_agent_max_turns = default_agent_max_turns
        if agent_tool is not None:
            self._agent_tool = agent_tool
        else:
            delegated_llm = subagent_llm_adapter or llm_adapter
            self._agent_tool = AgentTool(
                llm_adapter=delegated_llm,
                tool_registry=self._tool_registry,
                default_max_turns=default_agent_max_turns,
            )

    def run(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """Run the second-stage orchestrator loop synchronously."""

        state = self.initialize_run(task_input)
        invalid_action_count = 0
        max_main_turns = max(state.max_turns * 6, 6)

        while not state.done:
            if self._repair_iterations_used(state) >= state.max_turns:
                state.record_error(
                    make_error(
                        code=ORCH_MAX_ITERATIONS_EXCEEDED,
                        message="The orchestrator reached the maximum number of repair iterations.",
                        retryable=False,
                        stage=state.current_stage or "ORCHESTRATOR",
                        source="RepairOrchestrator",
                    )
                )
                state.mark_done(
                    final_status="NEED_HUMAN_REVIEW",
                    exit_reason="max_iterations_reached",
                    need_human_review=True,
                )
                break

            if state.turn_count >= max_main_turns:
                state.record_error(
                    make_error(
                        code=ORCH_MAX_MAIN_TURNS_REACHED,
                        message="The orchestrator reached the maximum number of main-thread turns.",
                        retryable=False,
                        stage=state.current_stage or "ORCHESTRATOR",
                        source="RepairOrchestrator",
                    )
                )
                state.mark_done(
                    final_status="NEED_HUMAN_REVIEW",
                    exit_reason="max_iterations_reached",
                    need_human_review=True,
                )
                break

            state.increment_turn()
            turn = self._llm_adapter.complete(
                messages=state.messages,
                tools=[self._agent_tool],
                system_prompt=self._build_system_prompt(),
                tool_use_context=state.tool_use_context,
            )

            if turn.kind == "final":
                state.add_message({"role": "assistant", "content": turn.content})
                self._finalize_from_main_turn(state, turn.content)
                break

            if turn.kind == "tool" and turn.tool_call:
                state.add_message({"role": "assistant", "content": turn.content})
                validation_error = self._validate_main_thread_action(state, turn.tool_call)
                if validation_error is not None:
                    invalid_action_count += 1
                    correction_message = self._build_orchestrator_feedback_message(validation_error)
                    state.add_message(correction_message)
                    state.record_error(validation_error)
                    if invalid_action_count >= 2:
                        state.mark_done(
                            final_status="NEED_HUMAN_REVIEW",
                            exit_reason="repeated_invalid_action",
                            need_human_review=True,
                        )
                    continue

                invalid_action_count = 0
                result = self._invoke_agent_tool(state, turn.tool_call)
                self._record_agent_observation(state, result)
                if self._should_escalate_after_agent_result(result):
                    state.mark_done(
                        final_status="NEED_HUMAN_REVIEW",
                        exit_reason=f"agent_result_{result.status}",
                        need_human_review=True,
                    )
                continue

            state.record_error(
                make_error(
                    code=ORCH_INVALID_MAIN_TURN,
                    message="The orchestrator LLM returned an unsupported turn.",
                    retryable=False,
                    stage=state.current_stage or "ORCHESTRATOR",
                    source="RepairOrchestrator",
                )
            )
            state.mark_done(
                final_status="NEED_HUMAN_REVIEW",
                exit_reason="invalid_main_turn",
                need_human_review=True,
            )

        return self.finalize_run(state)

    def initialize_run(self, task_input: dict[str, Any]) -> RepairRuntimeState:
        """Build the initial runtime state for one repair run."""

        run_id = str(task_input.get("run_id", ""))
        if not run_id:
            raise ValueError("task_input.run_id is required")

        max_iterations = int(task_input.get("max_iterations", self._default_max_iterations))
        state = RepairRuntimeState(
            run_id=run_id,
            bug_event=task_input.get("bug_event"),
            traceback=task_input.get("traceback"),
            repo_root=task_input.get("repo_root"),
            branch=task_input.get("branch"),
            max_turns=max_iterations,
            tool_use_context=ToolUseContext(
                allowed_tools=[self._agent_tool.name],
                read_only=False,
                repo_root=task_input.get("repo_root"),
                os_name=self._detect_os_name(),
                permission_mode="default",
            ),
            current_stage="ORCHESTRATOR",
        )
        state.messages.extend(self._build_initial_messages(task_input))
        return state

    def _detect_os_name(self) -> str:
        system = platform.system().strip().lower()
        if system.startswith("win"):
            return "windows"
        if system == "darwin":
            return "macos"
        return system or "unknown"

    def finalize_run(self, state: RepairRuntimeState) -> dict[str, Any]:
        """Return the top-level structured result for one repair run."""

        summary = self._derive_summary(state)
        return {
            "run_id": state.run_id,
            "final_status": state.final_status or "FAILED",
            "current_stage": state.current_stage or "ORCHESTRATOR",
            "iterations_used": self._repair_iterations_used(state),
            "summary": summary,
            "artifacts": state.artifacts,
            "errors": state.errors,
        }

    def _build_system_prompt(self) -> str:
        return build_orchestrator_system_prompt()

    def _build_initial_messages(self, task_input: dict[str, Any]) -> list[MessageLike]:
        return build_orchestrator_initial_messages(
            task_input,
            default_max_iterations=self._default_max_iterations,
        )

    def _validate_main_thread_action(
        self,
        state: RepairRuntimeState,
        tool_call: ToolCall,
    ) -> dict[str, Any] | None:
        if tool_call.name != self._agent_tool.name:
            return self._build_guardrail_error(
                code=ORCH_INVALID_TOOL_NAME,
                message=f"Main-thread orchestrator may only call `{self._agent_tool.name}`.",
                stage=state.current_stage,
            )

        agent_type = tool_call.arguments.get("agent_type")
        prompt = tool_call.arguments.get("prompt")
        user_prompt = tool_call.arguments.get("user_prompt")
        description = tool_call.arguments.get("description")
        if not isinstance(agent_type, str) or not agent_type:
            return self._build_guardrail_error(
                code=ORCH_MISSING_AGENT_TYPE,
                message="The `agent` tool call must include a non-empty agent_type.",
                stage=state.current_stage,
            )
        effective_prompt = prompt if isinstance(prompt, str) and prompt else user_prompt
        if not isinstance(effective_prompt, str) or not effective_prompt:
            return self._build_guardrail_error(
                code=ORCH_MISSING_USER_PROMPT,
                message="The `agent` tool call must include a non-empty prompt.",
                stage=state.current_stage,
            )
        if not isinstance(description, str) or not description:
            return self._build_guardrail_error(
                code=ORCH_MISSING_USER_PROMPT,
                message="The `agent` tool call must include a non-empty description.",
                stage=state.current_stage,
            )
        try:
            get_agent_definition(agent_type)
        except ValueError as exc:
            return self._build_guardrail_error(
                code=ORCH_INVALID_AGENT_TYPE,
                message=str(exc),
                stage=state.current_stage,
            )

        if state.last_agent_result is None and agent_type == "execute":
            return self._build_guardrail_error(
                code=ORCH_INVALID_STAGE_JUMP,
                message="The orchestrator cannot dispatch `execute` as the first step without prior context.",
                stage=state.current_stage,
            )
        return None

    def _build_guardrail_error(
        self,
        *,
        code: str,
        message: str,
        stage: str | None,
    ) -> dict[str, Any]:
        return make_error(
            code=code,
            message=message,
            retryable=True,
            stage=stage or "ORCHESTRATOR",
            source="RepairOrchestrator",
        )

    def _build_orchestrator_feedback_message(self, error: dict[str, Any]) -> MessageLike:
        return build_orchestrator_guardrail_feedback(str(error["message"]))

    def _invoke_agent_tool(self, state: RepairRuntimeState, tool_call: ToolCall) -> AgentToolResult:
        payload = self._build_agent_payload(state, tool_call)
        if hasattr(self._agent_tool, "invoke"):
            result = self._agent_tool.invoke(payload)
        else:
            arguments = dict(tool_call.arguments)
            arguments.setdefault("tool_use_context", state.tool_use_context)
            arguments.setdefault("max_turns", self._default_agent_max_turns)
            result = self._agent_tool.execute(**arguments)
        state.current_stage = result.agent_type
        return result

    def _build_agent_payload(self, state: RepairRuntimeState, tool_call: ToolCall) -> dict[str, Any]:
        arguments = dict(tool_call.arguments)
        agent_type = str(arguments["agent_type"])
        input_payload = self._build_agent_input_payload(state, agent_type, arguments)
        return {
            "run_id": state.run_id,
            "iteration": state.turn_count,
            "agent_tool": agent_type,
            "input": input_payload,
            "constraints": {
                "max_turns": int(arguments.get("max_turns", self._default_agent_max_turns)),
                "read_only": agent_type in {"explore", "plan", "verify"},
                "allowed_tools": [],
                "permission_mode": "plan" if agent_type in {"explore", "plan", "verify"} else "acceptEdits",
            },
            "tool_use_context": state.tool_use_context,
        }

    def _build_agent_input_payload(
        self,
        state: RepairRuntimeState,
        agent_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if agent_type == "verify":
            return {
                "description": str(arguments["description"]),
                "prompt": self._build_verify_brief(state, arguments),
            }
        return {
            "description": str(arguments["description"]),
            "prompt": str(arguments.get("prompt") or arguments["user_prompt"]),
        }

    def _build_verify_brief(
        self,
        state: RepairRuntimeState,
        arguments: dict[str, Any],
    ) -> str:
        requested_prompt = str(arguments.get("prompt") or arguments["user_prompt"])
        bug_event = state.bug_event or {}
        explore_output = ((state.artifacts.get("explore") or {}).get("output") or {})
        repair_context = explore_output.get("repair_context", {})
        plan_output = ((state.artifacts.get("plan") or {}).get("output") or {})
        execute_output = ((state.artifacts.get("execute") or {}).get("output") or {})
        patch_result = execute_output.get("patch_result", {})
        verification_targets = [
            "Original bug path validation",
            "Targeted tests/checks validation",
            "Regression or boundary validation",
        ]
        return (
            "Verification brief for the repaired web service bug.\n"
            f"Requested verification goal: {requested_prompt}\n"
            f"repo_root: {state.repo_root}\n"
            f"branch: {state.branch}\n"
            f"error_type: {bug_event.get('error_type')}\n"
            f"error_message: {bug_event.get('error_message')}\n"
            f"error_summary: {bug_event.get('error_summary')}\n"
            f"traceback_snippet: {state.traceback or bug_event.get('traceback') or ''}\n"
            f"suspect_files: {json.dumps(explore_output.get('suspect_files', []), ensure_ascii=False)}\n"
            f"related_context: {json.dumps(repair_context.get('code_snippets', []), ensure_ascii=False)}\n"
            f"suggested_tests_to_run: {json.dumps(plan_output.get('tests_to_run', []), ensure_ascii=False)}\n"
            f"modified_files: {json.dumps(patch_result.get('modified_files', []), ensure_ascii=False)}\n"
            f"patch_summary: {json.dumps(patch_result.get('patch_summary', []), ensure_ascii=False)}\n"
            "Verification targets:\n"
            f"- {verification_targets[0]}: reproduce the original traceback path when possible and confirm the failure no longer occurs.\n"
            f"- {verification_targets[1]}: run the most relevant tests or command-backed checks for the repaired code path.\n"
            f"- {verification_targets[2]}: perform at least one nearby regression or boundary probe.\n"
            "If any of these targets cannot be validated because context or environment is missing, state that explicitly and return PARTIAL instead of guessing.\n"
        )

    def _record_agent_observation(self, state: RepairRuntimeState, result: AgentToolResult) -> None:
        plan_fallback = self._apply_plan_fallback(state, result)
        state.record_agent_result(
            agent_tool=result.agent_type,
            result=result,
            transition_reason=f"agent_{result.status}",
            transition_source=result.agent_type,
            retryable=result.status != "failed",
        )
        state.artifacts[result.agent_type] = {
            "summary": result.summary,
            "status": result.status,
            "stop_reason": result.stop_reason,
            "used_tools": list(result.used_tools),
            "permission_mode": result.permission_mode,
            "read_only": result.read_only,
            "turn_count": result.turn_count,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "output": result.output,
            "artifacts": list(result.artifacts),
            "tool_calls": [self._serialize_tool_call(record) for record in result.tool_calls],
            "tool_results": [self._serialize_tool_result(record) for record in result.tool_results],
            "errors": list(result.errors),
        }
        if result.agent_type == "plan" and plan_fallback is not None:
            state.artifacts[result.agent_type]["fallback_used"] = plan_fallback.used
            state.artifacts[result.agent_type]["fallback_reason"] = plan_fallback.reason
            state.artifacts[result.agent_type]["fallback_files_to_modify"] = list(plan_fallback.files_to_modify)
        if result.agent_type == "verify":
            state.artifacts["_repair_iterations_used"] = self._repair_iterations_used(state) + 1
        state.add_message(self._build_agent_tool_result_message(result))
        if result.error:
            state.record_error(
                make_error(
                    code=ORCH_AGENT_TOOL_ERROR,
                    message=result.error,
                    retryable=False,
                    stage=result.agent_type,
                    source="RepairOrchestrator",
                )
            )

    def _serialize_tool_call(self, record: ToolCall) -> dict[str, Any]:
        return {
            "name": record.name,
            "arguments": dict(record.arguments),
        }

    def _serialize_tool_result(self, record: Any) -> dict[str, Any]:
        return {
            "name": record.name,
            "arguments": dict(record.arguments),
            "status": record.status,
            "output": record.output,
            "structured_output": record.structured_output,
            "summary": record.summary,
            "error": record.error,
        }

    def _build_agent_tool_result_message(self, result: AgentToolResult) -> MessageLike:
        observation = {
            "agent_type": result.agent_type,
            "status": result.status,
            "stop_reason": result.stop_reason,
            "summary": result.summary,
            "output": result.output,
            "artifacts": result.artifacts,
            "errors": result.errors,
            "used_tools": result.used_tools,
            "error": result.error,
            "permission_mode": result.permission_mode,
            "read_only": result.read_only,
        }
        return {
            "role": "tool",
            "name": self._agent_tool.name,
            "content": json.dumps(observation, ensure_ascii=False),
            "tool_result": {
                "type": "tool_result",
                "tool_name": self._agent_tool.name,
                "content": observation,
                "is_error": result.status == "failed",
            },
        }

    def _should_escalate_after_agent_result(self, result: AgentToolResult) -> bool:
        if result.status == "failed":
            return True
        if result.agent_type == "explore":
            return self._explore_requires_human_review(result)
        if result.agent_type == "plan":
            return self._plan_requires_human_review(result)
        return False

    def _explore_requires_human_review(self, result: AgentToolResult) -> bool:
        output = result.output
        context_completeness = output.get("context_completeness")
        suspect_files = output.get("suspect_files", [])
        repair_context = output.get("repair_context", {})
        code_snippets = repair_context.get("code_snippets", [])
        return (
            context_completeness != "sufficient"
            or not isinstance(suspect_files, list)
            or len(suspect_files) == 0
            or not isinstance(code_snippets, list)
            or len(code_snippets) == 0
        )

    def _plan_requires_human_review(self, result: AgentToolResult) -> bool:
        output = result.output
        repair_plan = output.get("repair_plan", {})
        files_to_modify = repair_plan.get("files_to_modify", [])
        evidence = output.get("root_cause_analysis", {}).get("evidence", [])
        return (
            not isinstance(files_to_modify, list)
            or len(files_to_modify) == 0
            or not isinstance(evidence, list)
            or len(evidence) == 0
        )

    def _apply_plan_fallback(
        self,
        state: RepairRuntimeState,
        result: AgentToolResult,
    ) -> PlanFallbackDecision | None:
        if result.agent_type != "plan":
            return None

        output = result.output
        root_cause_analysis = output.setdefault("root_cause_analysis", {})
        repair_plan = output.setdefault("repair_plan", {})
        files_to_modify = repair_plan.get("files_to_modify", [])
        evidence = root_cause_analysis.get("evidence", [])
        if isinstance(files_to_modify, list) and files_to_modify and isinstance(evidence, list) and evidence:
            return PlanFallbackDecision(
                used=False,
                allow_continue=True,
                reason="structured_plan_complete",
                files_to_modify=list(files_to_modify),
                evidence=list(evidence),
            )

        fallback = self._resolve_plan_fallback(state, result)
        if fallback.used and fallback.allow_continue:
            repair_plan["files_to_modify"] = list(fallback.files_to_modify)
            root_cause_analysis["evidence"] = list(fallback.evidence)
        return fallback

    def _resolve_plan_fallback(
        self,
        state: RepairRuntimeState,
        result: AgentToolResult,
    ) -> PlanFallbackDecision:
        explore_output = ((state.artifacts.get("explore") or {}).get("output") or {})
        repair_context = explore_output.get("repair_context", {})
        suspect_files = explore_output.get("suspect_files") or repair_context.get("suspect_files") or []
        code_snippets = repair_context.get("code_snippets") or []
        context_completeness = explore_output.get("context_completeness")
        if context_completeness != "sufficient":
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_explore_context_insufficient",
                files_to_modify=[],
                evidence=[],
            )
        if not isinstance(suspect_files, list) or len(suspect_files) == 0:
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_missing_suspect_files",
                files_to_modify=[],
                evidence=[],
            )
        if not isinstance(code_snippets, list) or len(code_snippets) == 0:
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_missing_code_snippets",
                files_to_modify=[],
                evidence=[],
            )

        output = result.output
        risk_level = str(
            (output.get("root_cause_analysis") or {}).get("risk_level")
            or (output.get("repair_plan") or {}).get("risk_level")
            or ""
        ).strip().lower()
        if risk_level in {"high", "critical"}:
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_high_risk_plan",
                files_to_modify=[],
                evidence=[],
            )

        summary = result.summary or ""
        matched_files = self._extract_plan_summary_file_matches(summary, suspect_files)
        if not matched_files:
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_no_actionable_file_match",
                files_to_modify=[],
                evidence=[],
            )
        if not self._has_clear_plan_action(summary, matched_files):
            return PlanFallbackDecision(
                used=True,
                allow_continue=False,
                reason="fallback_blocked_summary_lacks_clear_action",
                files_to_modify=list(matched_files),
                evidence=[],
            )

        evidence = self._build_fallback_evidence(summary, matched_files, code_snippets)
        return PlanFallbackDecision(
            used=True,
            allow_continue=True,
            reason="fallback_from_plan_summary_and_explore_context",
            files_to_modify=list(matched_files),
            evidence=evidence,
        )

    def _extract_plan_summary_file_matches(
        self,
        summary: str,
        suspect_files: list[str],
    ) -> list[str]:
        matched: list[str] = []
        summary_lower = summary.lower()
        exact_matches = [path for path in suspect_files if path.lower() in summary_lower]
        for path in exact_matches:
            if path not in matched:
                matched.append(path)

        basename_map: dict[str, list[str]] = {}
        suffix_map: dict[str, list[str]] = {}
        for path in suspect_files:
            normalized = path.replace("\\", "/")
            basename = normalized.rsplit("/", 1)[-1].lower()
            basename_map.setdefault(basename, []).append(path)
            parts = normalized.split("/")
            if len(parts) >= 2:
                suffix = "/".join(parts[-2:]).lower()
                suffix_map.setdefault(suffix, []).append(path)

        summary_tokens = re.findall(r"[A-Za-z0-9_./\\\\-]+", summary)
        for token in summary_tokens:
            lowered = token.replace("\\", "/").lower().strip(".,:;`()[]{}<>\"'")
            if not lowered:
                continue
            if lowered in suffix_map and len(suffix_map[lowered]) == 1:
                candidate = suffix_map[lowered][0]
                if candidate not in matched:
                    matched.append(candidate)
            if lowered in basename_map and len(basename_map[lowered]) == 1:
                candidate = basename_map[lowered][0]
                if candidate not in matched:
                    matched.append(candidate)
        return matched

    def _has_clear_plan_action(self, summary: str, matched_files: list[str]) -> bool:
        if not matched_files:
            return False

        summary_lower = summary.lower()
        action_terms = (
            "modify",
            "change",
            "add",
            "update",
            "catch",
            "validate",
            "return",
            "raise",
            "fix",
            "replace",
            "remove",
            "handle",
            "guard",
            "patch",
            "edit",
            "调整",
            "修改",
            "新增",
            "添加",
            "更新",
            "捕获",
            "校验",
            "返回",
            "抛出",
            "修复",
            "替换",
            "删除",
            "处理",
        )
        uncertainty_terms = (
            "suggest",
            "recommend",
            "maybe",
            "possible",
            "might",
            "confirm",
            "need more",
            "further analysis",
            "further investigate",
            "unclear",
            "consider",
            "建议",
            "确认",
            "可能",
            "需要进一步",
            "进一步分析",
            "进一步确认",
            "也许",
        )
        has_action = any(term in summary_lower for term in action_terms)
        has_uncertainty = any(term in summary_lower for term in uncertainty_terms)
        if has_action:
            return True
        if has_uncertainty:
            return False
        return False

    def _build_fallback_evidence(
        self,
        summary: str,
        matched_files: list[str],
        code_snippets: list[dict[str, Any]],
    ) -> list[str]:
        evidence: list[str] = []
        for path in matched_files:
            evidence.append(f"Fallback matched plan summary to suspect file: {path}")
        snippet_text = "\n".join(str(snippet.get("content", "")) for snippet in code_snippets)
        for path in matched_files:
            basename = path.replace("\\", "/").rsplit("/", 1)[-1]
            if basename and basename in snippet_text:
                evidence.append(f"Explore captured code context for {path}")
        if "traceback" in summary.lower():
            evidence.append("Plan summary references traceback-derived failure context")
        if not evidence:
            evidence.append("Fallback accepted plan summary as actionable against explore context")
        return evidence

    def _finalize_from_main_turn(self, state: RepairRuntimeState, final_text: str) -> None:
        verification_output = (state.artifacts.get("verify") or {}).get("output", {})
        verification_result = verification_output.get("verification_result", {})
        verification_report = str(verification_output.get("verification_report", ""))
        verdict = str(verification_result.get("verdict") or "").upper().strip()
        if not verdict and verification_report:
            verdict = self._infer_verification_report_verdict(verification_report)
        ready_for_pr = verification_result.get("ready_for_pr")
        if verdict == "PASS" or ready_for_pr is True:
            state.mark_done(
                final_status="READY_FOR_PR",
                exit_reason="verify_passed",
                ready_for_pr=True,
            )
            return

        normalized = final_text.upper()
        if "READY_FOR_PR" in normalized:
            state.mark_done(
                final_status="READY_FOR_PR",
                exit_reason="main_thread_final",
                ready_for_pr=True,
            )
            return
        if "NEED_HUMAN_REVIEW" in normalized:
            state.mark_done(
                final_status="NEED_HUMAN_REVIEW",
                exit_reason="main_thread_final",
                need_human_review=True,
            )
            return
        if "FAILED" in normalized:
            state.mark_done(
                final_status="FAILED",
                exit_reason="main_thread_final",
            )
            return
        state.mark_done(
            final_status="NEED_HUMAN_REVIEW",
            exit_reason="main_thread_final",
            need_human_review=True,
        )

    def _derive_summary(self, state: RepairRuntimeState) -> str:
        if isinstance(state.last_agent_result, AgentToolResult):
            return state.last_agent_result.summary
        if state.messages:
            last_message = state.messages[-1]
            return str(last_message.get("content", ""))
        return ""

    def _repair_iterations_used(self, state: RepairRuntimeState) -> int:
        return int(state.artifacts.get("_repair_iterations_used", 0))

    def _infer_verification_report_verdict(self, verification_report: str) -> str:
        normalized = verification_report.upper()
        if "VERDICT: PASS" in normalized:
            return "PASS"
        if "VERDICT: FAIL" in normalized:
            return "FAIL"
        if "VERDICT: PARTIAL" in normalized:
            return "PARTIAL"
        return ""


def run(
    task_input: dict[str, Any],
    *,
    llm_adapter: LLMAdapter,
    agent_tool: BaseTool | None = None,
    subagent_llm_adapter: LLMAdapter | None = None,
    tool_registry: ToolRegistry | None = None,
    default_max_iterations: int = 3,
    default_agent_max_turns: int = 6,
) -> dict[str, Any]:
    """Module-level helper mirroring the planned synchronous orchestrator entrypoint."""

    orchestrator = RepairOrchestrator(
        llm_adapter=llm_adapter,
        agent_tool=agent_tool,
        subagent_llm_adapter=subagent_llm_adapter,
        tool_registry=tool_registry,
        default_max_iterations=default_max_iterations,
        default_agent_max_turns=default_agent_max_turns,
    )
    return orchestrator.run(task_input)
