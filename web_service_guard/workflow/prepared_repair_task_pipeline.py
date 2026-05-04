"""Bridge phase one and workspace preparation into a phase-two-ready payload."""

from __future__ import annotations

from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.workspace.repo_workspace_manager import RepoWorkspaceManager


class PreparedRepairTaskPipeline:
    """Run phase one and repository preparation as one cohesive pre-repair flow."""

    def __init__(
        self,
        *,
        sentinel_agent: SentinelAgent | None = None,
        workspace_manager: RepoWorkspaceManager | None = None,
    ) -> None:
        self.sentinel_agent = sentinel_agent or SentinelAgent()
        self.workspace_manager = workspace_manager or RepoWorkspaceManager()

    def run(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        repo_root: str | None = None,
        source: str = "log",
        metadata: dict | None = None,
    ) -> list[PreparedRepairTask]:
        repair_tasks = self.sentinel_agent.detect_and_create_tasks(
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
