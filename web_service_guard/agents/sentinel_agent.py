"""Phase-one Sentinel Agent for detecting incidents and building repair tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from web_service_guard.config import config
from web_service_guard.monitoring.dedup_store import InMemoryDedupStore
from web_service_guard.monitoring.event_detector import EventDetector
from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.incident_trigger import IncidentTrigger
from web_service_guard.schemas.repair_task import RepairTask
from web_service_guard.workflow.repair_task_factory import RepairTaskFactory
from web_service_guard.workflow.stage_router import StageRouter


class SentinelAgent:
    """First-phase orchestrator that turns incidents into repair tasks."""

    def __init__(
        self,
        *,
        traceback_collector: TracebackCollector | None = None,
        event_detector: EventDetector | None = None,
        dedup_store: InMemoryDedupStore | None = None,
        repair_task_factory: RepairTaskFactory | None = None,
        max_iterations: int | None = None,
    ) -> None:
        self.traceback_collector = traceback_collector or TracebackCollector(
            log_path=config.default_runtime_log_path
        )
        self.event_detector = event_detector or EventDetector()
        self.dedup_store = dedup_store or InMemoryDedupStore(
            ttl_sec=config.stage_one_dedup_ttl_sec
        )
        self.repair_task_factory = repair_task_factory or RepairTaskFactory(
            default_max_iterations=max_iterations or config.max_iterations
        )
        self.max_iterations = max_iterations or config.max_iterations

    def build_trigger(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        source: str = "log",
        metadata: dict[str, Any] | None = None,
    ) -> IncidentTrigger:
        return IncidentTrigger(
            source=source,
            service=service or config.default_service_name,
            repo=repo or config.default_repo_url,
            branch=branch or config.default_branch,
            detected_at=_utc_now(),
            metadata=dict(metadata or {}),
        )

    def collect_bug_events(self, trigger: IncidentTrigger) -> list[BugEvent]:
        candidates = self.traceback_collector.collect_tracebacks(
            service=trigger.service,
            source=trigger.source,
            detected_at=trigger.detected_at,
        )
        return self.event_detector.detect_events(
            candidates,
            service=trigger.service,
            repo=trigger.repo,
            branch=trigger.branch,
            source=trigger.source,
            detected_at=trigger.detected_at,
        )

    def create_repair_tasks(
        self,
        trigger: IncidentTrigger,
        *,
        repo_root: str,
    ) -> list[RepairTask]:
        tasks: list[RepairTask] = []
        for bug_event in self.collect_bug_events(trigger):
            if self.dedup_store.is_duplicate(
                bug_event.fingerprint,
                seen_at=bug_event.detected_at,
            ):
                continue
            decision = StageRouter.evaluate_bug_event(bug_event)
            if not decision.accepted:
                continue
            tasks.append(
                self.repair_task_factory.build(
                    bug_event=bug_event,
                    repo_root=repo_root,
                    max_iterations=self.max_iterations,
                    metadata={"trigger": trigger.to_dict()},
                )
            )
        return tasks

    def detect_and_create_tasks(
        self,
        *,
        service: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        repo_root: str | None = None,
        source: str = "log",
        metadata: dict[str, Any] | None = None,
    ) -> list[RepairTask]:
        """Collect incidents and return formal repair tasks for downstream phases."""

        trigger = self.build_trigger(
            service=service,
            repo=repo,
            branch=branch,
            source=source,
            metadata=metadata,
        )
        return self.create_repair_tasks(
            trigger,
            repo_root=repo_root or config.default_repo_root,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
