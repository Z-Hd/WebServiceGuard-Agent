"""Main Repair Orchestrator entry point that owns the second-stage repair loop."""

from __future__ import annotations

import json
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
    VERIFY_TARGETED_TEST_FAILED,
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
            finalization_only_turn = False
            if self._repair_iterations_used(state) >= state.max_turns and "verify" in state.artifacts:
                if state.post_verify_finalization_pending:
                    finalization_only_turn = True
                    state.post_verify_finalization_pending = False
                else:
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
                tools=[] if finalization_only_turn else [self._agent_tool],
                system_prompt=self._build_system_prompt(),
                tool_use_context=state.tool_use_context,
            )

            if turn.kind == "final":
                state.add_message({"role": "assistant", "content": turn.content})
                self._finalize_from_main_turn(state, turn.content)
                break

            if turn.kind == "tool" and turn.tool_call:
                if finalization_only_turn:
                    state.record_error(
                        make_error(
                            code=ORCH_MAX_ITERATIONS_EXCEEDED,
                            message="The orchestrator must finalize after the last verification instead of dispatching another agent.",
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
            repo=task_input.get("repo"),
            branch=task_input.get("branch"),
            max_turns=max_iterations,
            tool_use_context=ToolUseContext(
                allowed_tools=[self._agent_tool.name],
                read_only=False,
                repo_root=task_input.get("repo"),
                permission_mode="default",
            ),
            current_stage="ORCHESTRATOR",
        )
        state.messages.extend(self._build_initial_messages(task_input))
        return state

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
        return {
            "description": str(arguments["description"]),
            "prompt": str(arguments.get("prompt") or arguments["user_prompt"]),
        }

    def _record_agent_observation(self, state: RepairRuntimeState, result: AgentToolResult) -> None:
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
            "output": result.output,
            "artifacts": list(result.artifacts),
            "errors": list(result.errors),
        }
        if result.agent_type == "verify":
            state.artifacts["_repair_iterations_used"] = self._repair_iterations_used(state) + 1
            state.post_verify_finalization_pending = True
        else:
            state.post_verify_finalization_pending = False
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
        if result.agent_type == "execute":
            return self._execute_requires_human_review(result)
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
        need_human_review = output.get("need_human_review")
        return (
            need_human_review is True
            or not isinstance(files_to_modify, list)
            or len(files_to_modify) == 0
            or not isinstance(evidence, list)
            or len(evidence) == 0
        )

    def _execute_requires_human_review(self, result: AgentToolResult) -> bool:
        output = result.output
        patch_result = output.get("patch_result", {})
        modified_files = patch_result.get("modified_files", [])
        need_replan = output.get("need_replan")
        return (
            need_replan is True
            or not isinstance(modified_files, list)
            or len(modified_files) == 0
        )

    def _finalize_from_main_turn(self, state: RepairRuntimeState, final_text: str) -> None:
        verification_output = (state.artifacts.get("verify") or {}).get("output", {})
        verification_result = verification_output.get("verification_result", {})
        verdict = verification_result.get("verdict")
        ready_for_pr = verification_result.get("ready_for_pr")
        if verdict == "PASS" and ready_for_pr is True:
            state.mark_done(
                final_status="READY_FOR_PR",
                exit_reason="verify_passed",
                ready_for_pr=True,
            )
            return
        if verdict in {"FAIL", "PARTIAL"}:
            self._record_verify_failure_error(state, verification_result)
            state.mark_done(
                final_status="NEED_HUMAN_REVIEW",
                exit_reason="verify_not_ready",
                need_human_review=True,
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

    def _record_verify_failure_error(
        self,
        state: RepairRuntimeState,
        verification_result: dict[str, Any],
    ) -> None:
        verdict = verification_result.get("verdict")
        if verdict == "FAIL":
            state.record_error(
                make_error(
                    code=VERIFY_TARGETED_TEST_FAILED,
                    message="Verification reported FAIL.",
                    retryable=False,
                    stage="VERIFY",
                    source="RepairOrchestrator",
                )
            )


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
