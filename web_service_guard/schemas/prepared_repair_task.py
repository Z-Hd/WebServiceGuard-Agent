"""Schema for a repair task whose local repository workspace is ready."""

from __future__ import annotations

from dataclasses import dataclass

from web_service_guard.schemas.repo_workspace import RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


@dataclass(slots=True)
class PreparedRepairTask:
    """Bundle the repair task and prepared workspace for phase two consumption."""

    repair_task: RepairTask
    workspace: RepoWorkspaceResult

    @property
    def workspace_ready(self) -> bool:
        return bool(self.workspace.workspace_ready)

    def to_dict(self) -> dict:
        return {
            "repair_task": self.repair_task.to_dict(),
            "workspace": self.workspace.to_dict(),
        }
