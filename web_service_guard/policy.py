"""Guardrail and policy checks that constrain automatic repair behavior."""
<<<<<<< HEAD

from __future__ import annotations


class Policy:
    """Minimal guardrail policy helpers used by workflow routing."""

    HIGH_RISK_LEVELS = {"high", "critical"}

    @staticmethod
    def should_proceed_to_pr(verification_result: dict | None) -> bool:
        if not isinstance(verification_result, dict):
            return False
        if "ready_for_pr" in verification_result:
            return bool(verification_result.get("ready_for_pr"))
        return bool(
            verification_result.get("targeted_tests_passed")
            and verification_result.get("smoke_tests_passed")
        )

    @staticmethod
    def should_escalate_for_risk(risk_level: str | None) -> bool:
        if not risk_level:
            return False
        return str(risk_level).strip().lower() in Policy.HIGH_RISK_LEVELS
=======
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
