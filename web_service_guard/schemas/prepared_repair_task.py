"""Schema for a repair task whose local repository workspace is ready."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    def to_stage_two_input(self) -> dict[str, Any]:
        """Adapt the prepared task into the flat task_input expected by stage two."""

        branch = (
            self.workspace.repair_branch
            or self.workspace.current_branch
            or self.repair_task.bug_event.branch
        )
        return {
            "run_id": self.repair_task.run_id,
            "bug_event": self.repair_task.bug_event.to_dict(),
            "traceback": self.repair_task.bug_event.traceback,
            "repo_root": self.workspace.repo_root,
            "branch": branch,
            "max_iterations": self.repair_task.max_iterations,
        }

    def to_dict(self) -> dict:
        return {
            "repair_task": self.repair_task.to_dict(),
            "workspace": self.workspace.to_dict(),
        }
