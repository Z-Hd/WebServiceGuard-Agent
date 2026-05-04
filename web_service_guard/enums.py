"""Shared enumerations for statuses, risks, tool results, and audit event types."""

from __future__ import annotations

from enum import Enum


class FinalStatus(str, Enum):
    READY_FOR_PR = "READY_FOR_PR"
    NEED_HUMAN_REVIEW = "NEED_HUMAN_REVIEW"
    FAILED = "FAILED"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
