from __future__ import annotations

from dataclasses import dataclass

from web_service_guard.enums import FinalStatus
from web_service_guard.policy import Policy
from web_service_guard.schemas.bug_event import BugEvent


@dataclass(slots=True)
class StageOneDecision:
    accepted: bool
    reason: str
    code: str


class StageRouter:
    """Stage-one and stage-transition routing helpers."""

    @staticmethod
    def evaluate_bug_event(bug_event: BugEvent) -> StageOneDecision:
        if not bug_event.traceback.strip():
            return StageOneDecision(False, "缺少有效 Traceback", "S1_TRACEBACK_MISSING")
        if not bug_event.repo.strip():
            return StageOneDecision(False, "缺少仓库信息", "S1_REPO_MISSING")
        if not bug_event.branch.strip():
            return StageOneDecision(False, "缺少分支信息", "S1_BRANCH_MISSING")
        return StageOneDecision(True, "可以进入修复阶段", "S1_EVENT_ACCEPTED")

    @staticmethod
    def should_proceed_to_pr(verification_result):
        return Policy.should_proceed_to_pr(verification_result)

    @staticmethod
    def should_escalate(risk_level, errors):
        if risk_level and Policy.should_escalate_for_risk(risk_level):
            return True, "高风险操作"
        if errors:
            for error in errors:
                if not error.get("retryable"):
                    return True, "不可重试的错误"
        return False, "不需要升级"

    @staticmethod
    def route(repair_result):
        final_status = repair_result.get("final_status")
        if final_status == FinalStatus.READY_FOR_PR.value:
            return "PR"
        if final_status == FinalStatus.NEED_HUMAN_REVIEW.value:
            return "HUMAN_REVIEW"
        if final_status == FinalStatus.FAILED.value:
            return "FAILED"
        return "UNKNOWN"
