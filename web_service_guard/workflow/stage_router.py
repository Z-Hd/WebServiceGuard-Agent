from __future__ import annotations

from web_service_guard.enums import FinalStatus
from web_service_guard.policy import Policy


class StageRouter:
    """Stage-transition routing helpers shared by later phases."""

    @staticmethod
    def should_proceed_to_pr(verification_result):
        return Policy.should_proceed_to_pr(verification_result)

    @staticmethod
    def should_escalate(risk_level, errors):
        if risk_level and Policy.should_escalate_for_risk(risk_level):
            return True, "high risk operation"
        if errors:
            for error in errors:
                if not error.get("retryable"):
                    return True, "non-retryable error"
        return False, "no escalation needed"

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
