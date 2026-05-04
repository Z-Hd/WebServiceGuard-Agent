"""Schema for invoking the third-stage delivery pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask


@dataclass(slots=True)
class DeliveryRequest:
    """Bundle prepared workspace context and repair output for stage-three delivery."""

    prepared_task: PreparedRepairTask | dict[str, Any]
    repair_result: dict[str, Any]
    notification_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        prepared_task = (
            self.prepared_task.to_dict()
            if hasattr(self.prepared_task, "to_dict")
            else dict(self.prepared_task)
        )
        return {
            "prepared_task": prepared_task,
            "repair_result": dict(self.repair_result),
            "notification_enabled": self.notification_enabled,
        }
