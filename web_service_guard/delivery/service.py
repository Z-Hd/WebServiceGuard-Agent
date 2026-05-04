"""Main third-stage delivery orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_service_guard.delivery.git_delivery import GitDelivery
from web_service_guard.delivery.notify_service import NotifyService
from web_service_guard.delivery.pr_service import PRService
from web_service_guard.errors import (
    DELIVERY_GATE_FAILED,
    DELIVERY_GIT_FAILED,
    DELIVERY_INPUT_INVALID,
    DELIVERY_NOTIFY_FAILED,
    DELIVERY_PR_FAILED,
    make_error,
)
from web_service_guard.policy import Policy
from web_service_guard.schemas.delivery_request import DeliveryRequest
from web_service_guard.schemas.delivery_result import DeliveryResult


DELIVERY_STAGE = "DELIVERY"


@dataclass(slots=True)
class DeliveryGateOutcome:
    """Internal result for deciding whether delivery may proceed."""

    passed: bool
    summary: str
    errors: list[dict[str, Any]]


class DeliveryService:
    """Coordinate git publication, PR creation, and notification delivery."""

    def __init__(
        self,
        *,
        git_delivery: GitDelivery | None = None,
        pr_service: PRService | None = None,
        notify_service: NotifyService | None = None,
    ) -> None:
        self._git_delivery = git_delivery or GitDelivery()
        self._pr_service = pr_service or PRService()
        self._notify_service = notify_service or NotifyService()

    def run(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        notification_enabled: bool = True,
    ) -> dict[str, Any]:
        request = DeliveryRequest(
            prepared_task=prepared_task,
            repair_result=repair_result,
            notification_enabled=notification_enabled,
        )
        return self.run_request(request).to_dict()

    def run_request(self, request: DeliveryRequest) -> DeliveryResult:
        run_id = str(request.repair_result.get("run_id", "")).strip()
        if not run_id:
            return DeliveryResult(
                run_id="",
                status="FAILED",
                gate_passed=False,
                summary="Delivery request is missing run_id.",
                errors=[
                    make_error(
                        code=DELIVERY_INPUT_INVALID,
                        message="Delivery request is missing repair_result.run_id.",
                        retryable=False,
                        stage=DELIVERY_STAGE,
                        source="DeliveryService",
                    )
                ],
            )

        gate = self._evaluate_gate(request.prepared_task, request.repair_result)
        workspace = _extract_workspace(request.prepared_task)
        repo_root = str(workspace.get("repo_root", "")).strip() or None
        repair_branch = _resolve_repair_branch(request.prepared_task)
        artifacts = self._build_delivery_artifacts(request.prepared_task, request.repair_result)
        if not gate.passed:
            return DeliveryResult(
                run_id=run_id,
                status="SKIPPED",
                gate_passed=False,
                summary=gate.summary,
                repo_root=repo_root,
                repair_branch=repair_branch,
                artifacts=artifacts,
                errors=gate.errors,
            )

        commit_message = self._build_commit_message(request.prepared_task, request.repair_result)
        publish_result = self._git_delivery.publish(
            repo_root=repo_root or "",
            branch_name=repair_branch or "",
            commit_message=commit_message,
        ).to_dict()
        artifacts["git"] = {
            "commit_message": commit_message,
            "diff_stat": publish_result.get("diff_stat", ""),
        }
        if not publish_result.get("created"):
            return DeliveryResult(
                run_id=run_id,
                status="FAILED",
                gate_passed=True,
                summary="Git publication failed.",
                repo_root=repo_root,
                repair_branch=repair_branch,
                commit=publish_result,
                artifacts=artifacts,
                errors=[
                    make_error(
                        code=DELIVERY_GIT_FAILED,
                        message=str(publish_result.get("error", "Git publication failed.")),
                        retryable=False,
                        stage=DELIVERY_STAGE,
                        source="GitDelivery",
                    )
                ],
            )

        pr_result = self._pr_service.create_pr(
            prepared_task=request.prepared_task,
            repair_result=request.repair_result,
            publish_result=publish_result,
        )
        if not pr_result.get("created"):
            return DeliveryResult(
                run_id=run_id,
                status="FAILED",
                gate_passed=True,
                summary="PR creation failed.",
                repo_root=repo_root,
                repair_branch=repair_branch,
                commit=publish_result,
                pr=pr_result,
                artifacts=artifacts,
                errors=[
                    make_error(
                        code=DELIVERY_PR_FAILED,
                        message=str(pr_result.get("error", "PR creation failed.")),
                        retryable=False,
                        stage=DELIVERY_STAGE,
                        source="PRService",
                    )
                ],
            )

        notification = {"sent": False, "channel": "feishu", "skipped": not request.notification_enabled}
        errors: list[dict[str, Any]] = []
        status = "SUCCESS"
        summary = "PR created and notification delivered."
        if request.notification_enabled:
            notification = self._notify_service.send_notification(
                prepared_task=request.prepared_task,
                repair_result=request.repair_result,
                pr_result=pr_result,
            )
            if not notification.get("sent"):
                status = "PARTIAL"
                summary = "PR created, but notification delivery failed."
                errors.append(
                    make_error(
                        code=DELIVERY_NOTIFY_FAILED,
                        message=str(notification.get("error", "Notification delivery failed.")),
                        retryable=True,
                        stage=DELIVERY_STAGE,
                        source="NotifyService",
                    )
                )
            else:
                summary = "PR created and notification delivered."
        else:
            summary = "PR created; notification was skipped."

        return DeliveryResult(
            run_id=run_id,
            status=status,
            gate_passed=True,
            summary=summary,
            repo_root=repo_root,
            repair_branch=repair_branch,
            commit=publish_result,
            pr=pr_result,
            notification=notification,
            artifacts=artifacts,
            errors=errors,
        )

    def _evaluate_gate(
        self,
        prepared_task: Any,
        repair_result: dict[str, Any],
    ) -> DeliveryGateOutcome:
        errors: list[dict[str, Any]] = []
        workspace = _extract_workspace(prepared_task)
        repair_result_status = str(repair_result.get("final_status", "")).strip()
        if repair_result_status != "READY_FOR_PR":
            errors.append(
                make_error(
                    code=DELIVERY_GATE_FAILED,
                    message="Repair result is not READY_FOR_PR.",
                    retryable=False,
                    stage=DELIVERY_STAGE,
                    source="DeliveryService",
                )
            )

        if not bool(workspace.get("workspace_ready")):
            errors.append(
                make_error(
                    code=DELIVERY_GATE_FAILED,
                    message="Prepared workspace is not ready.",
                    retryable=False,
                    stage=DELIVERY_STAGE,
                    source="DeliveryService",
                )
            )

        if not str(workspace.get("repo_root", "")).strip():
            errors.append(
                make_error(
                    code=DELIVERY_GATE_FAILED,
                    message="Prepared workspace is missing repo_root.",
                    retryable=False,
                    stage=DELIVERY_STAGE,
                    source="DeliveryService",
                )
            )

        if not _resolve_repair_branch(prepared_task):
            errors.append(
                make_error(
                    code=DELIVERY_GATE_FAILED,
                    message="Prepared workspace is missing a publishable branch.",
                    retryable=False,
                    stage=DELIVERY_STAGE,
                    source="DeliveryService",
                )
            )

        verification_result = (((repair_result.get("artifacts") or {}).get("verify") or {}).get("output") or {}).get(
            "verification_result"
        )
        if not Policy.should_proceed_to_pr(verification_result):
            errors.append(
                make_error(
                    code=DELIVERY_GATE_FAILED,
                    message="Verification output does not allow PR delivery.",
                    retryable=False,
                    stage=DELIVERY_STAGE,
                    source="DeliveryService",
                )
            )

        if errors:
            return DeliveryGateOutcome(
                passed=False,
                summary="Delivery gate did not pass.",
                errors=errors,
            )
        return DeliveryGateOutcome(
            passed=True,
            summary="Delivery gate passed.",
            errors=[],
        )

    def _build_commit_message(self, prepared_task: Any, repair_result: dict[str, Any]) -> str:
        bug_event = _extract_bug_event(prepared_task)
        service = str(bug_event.get("service", "")).strip() or "service"
        error_type = str(bug_event.get("error_type", "")).strip()
        if error_type:
            return f"Auto-fix: {service} - {error_type}"
        summary = str(bug_event.get("error_summary", "")).strip() or f"repair {repair_result.get('run_id', '')}"
        return f"Auto-fix: {summary[:72]}"

    def _build_delivery_artifacts(self, prepared_task: Any, repair_result: dict[str, Any]) -> dict[str, Any]:
        bug_event = _extract_bug_event(prepared_task)
        artifacts = repair_result.get("artifacts", {})
        plan_output = ((artifacts.get("plan") or {}).get("output") or {})
        execute_output = ((artifacts.get("execute") or {}).get("output") or {})
        verify_output = ((artifacts.get("verify") or {}).get("output") or {})
        verification = verify_output.get("verification_result") or {}
        return {
            "service": bug_event.get("service"),
            "error_summary": bug_event.get("error_summary"),
            "root_cause": ((plan_output.get("root_cause_analysis") or {}).get("root_cause")),
            "files_to_modify": (plan_output.get("repair_plan") or {}).get("files_to_modify") or [],
            "modified_files": (execute_output.get("patch_result") or {}).get("modified_files") or [],
            "verification_verdict": verification.get("verdict"),
            "ready_for_pr": verification.get("ready_for_pr"),
        }


def _extract_workspace(prepared_task: Any) -> dict[str, Any]:
    workspace = getattr(prepared_task, "workspace", None)
    if workspace is not None and hasattr(workspace, "to_dict"):
        return workspace.to_dict()
    if isinstance(prepared_task, dict):
        return dict(prepared_task.get("workspace") or {})
    return {}


def _extract_bug_event(prepared_task: Any) -> dict[str, Any]:
    repair_task = getattr(prepared_task, "repair_task", None)
    if repair_task is not None:
        bug_event = getattr(repair_task, "bug_event", None)
        if bug_event is not None and hasattr(bug_event, "to_dict"):
            return bug_event.to_dict()
    if isinstance(prepared_task, dict):
        return dict((prepared_task.get("repair_task") or {}).get("bug_event") or {})
    return {}


def _resolve_repair_branch(prepared_task: Any) -> str | None:
    workspace = _extract_workspace(prepared_task)
    for key in ("repair_branch", "current_branch", "branch"):
        value = str(workspace.get(key, "")).strip()
        if value:
            return value
    return None
