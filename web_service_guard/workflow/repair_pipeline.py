from __future__ import annotations

from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repair_task import RepairTask
from web_service_guard.workspace.repo_workspace_manager import RepoWorkspaceManager


class StageOnePipeline:
    """Unified phase-one entrypoint for task emission and workspace preparation."""

    def __init__(
        self,
        *,
        sentinel_agent: SentinelAgent | None = None,
        workspace_manager: RepoWorkspaceManager | None = None,
    ) -> None:
        self.sentinel_agent = sentinel_agent or SentinelAgent()
        self.workspace_manager = workspace_manager or RepoWorkspaceManager()

    def run_tasks(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        repo_root: str | None = None,
        source: str = "log",
        metadata: dict | None = None,
    ) -> list[RepairTask]:
        """Run phase one and return formal repair tasks."""

        return self.sentinel_agent.detect_and_create_tasks(
            service=service,
            repo=repo,
            branch=branch,
            repo_root=repo_root,
            source=source,
            metadata=metadata,
        )

    def run_prepared_tasks(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        repo_root: str | None = None,
        source: str = "log",
        metadata: dict | None = None,
    ) -> list[PreparedRepairTask]:
        """Run phase one and return phase-two-ready prepared repair tasks."""

        repair_tasks = self.run_tasks(
            service=service,
            repo=repo,
            branch=branch,
            repo_root=repo_root,
            source=source,
            metadata=metadata,
        )
        return [
            self.workspace_manager.prepare_prepared_task(repair_task)
            for repair_task in repair_tasks
        ]

    def run_stage_two_inputs(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        repo_root: str | None = None,
        source: str = "log",
        metadata: dict | None = None,
    ) -> list[dict]:
        """Run phase one and return stage-two-ready task_input dictionaries."""

        prepared_tasks = self.run_prepared_tasks(
            service=service,
            repo=repo,
            branch=branch,
            repo_root=repo_root,
            source=source,
            metadata=metadata,
        )
        return [
            prepared_task.to_stage_two_input()
            for prepared_task in prepared_tasks
        ]

    def run(self, service=None, repo=None, branch=None, repo_root=None):
        """Compatibility wrapper returning serialized repair-task payloads."""

        try:
            tasks = self.run_tasks(
                service=service,
                repo=repo,
                branch=branch,
                repo_root=repo_root,
            )
            if not tasks:
                return {
                    "status": "NO_EVENTS",
                    "message": "未发现可进入修复阶段的事件",
                }
            return {
                "status": "READY_FOR_REPAIR",
                "tasks": [task.to_dict() for task in tasks],
            }
        except Exception as exc:  # pragma: no cover - defensive wrapper
            return {
                "status": "FAILED",
                "message": str(exc),
            }


RepairPipeline = StageOnePipeline
