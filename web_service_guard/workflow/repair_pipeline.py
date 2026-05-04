from __future__ import annotations

from web_service_guard.agents.sentinel_agent import SentinelAgent


class RepairPipeline:
    """Phase-one pipeline shim that returns formal repair tasks."""

    def __init__(
        self,
        *,
        sentinel_agent: SentinelAgent | None = None,
    ) -> None:
        self.sentinel_agent = sentinel_agent or SentinelAgent()

    def run(self, service=None, repo=None, branch=None, repo_root=None):
        """Run phase one and return serialized repair tasks."""

        try:
            tasks = self.sentinel_agent.detect_and_create_tasks(
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
