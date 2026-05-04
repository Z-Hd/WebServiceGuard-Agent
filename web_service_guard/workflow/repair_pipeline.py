<<<<<<< HEAD
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
=======
from web_service_guard.runtime.orchestrator import RepairOrchestrator
from web_service_guard.monitoring.event_detector import EventDetector
from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.delivery.pr_service import PRService
from web_service_guard.delivery.notify_service import NotifyService
from web_service_guard.enums import FinalStatus

class RepairPipeline:
    """修复流水线"""
    
    def __init__(self):
        self.event_detector = EventDetector()
        self.traceback_collector = TracebackCollector()
        self.orchestrator = RepairOrchestrator()
        self.pr_service = PRService()
        self.notify_service = NotifyService()
    
    def run(self, service, repo, branch):
        """运行修复流水线"""
        try:
            # 第一阶段：异常感知与Traceback获取
            tracebacks = self.traceback_collector.collect_tracebacks()
            if not tracebacks:
                return {
                    "status": "NO_ERRORS",
                    "message": "未发现错误"
                }
            
            # 生成BugEvent
            events = self.event_detector.detect_events(tracebacks, service, repo, branch)
            if not events:
                return {
                    "status": "NO_EVENTS",
                    "message": "未生成修复事件"
                }
            
            # 处理每个BugEvent
            results = []
            for event in events:
                # 第二阶段：自动修复
                repair_result = self.orchestrator.run({
                    "run_id": f"repair_{event.timestamp}",
                    "bug_event": event.to_dict(),
                    "traceback": event.traceback,
                    "repo": repo,
                    "branch": branch,
                    "max_iterations": 3
                })
                
                # 第三阶段：PR提交与通知
                if repair_result.get('final_status') == FinalStatus.READY_FOR_PR.value:
                    # 创建PR
                    pr_result = self.pr_service.create_pr(
                        event=event,
                        repair_result=repair_result
                    )
                    
                    # 发送通知
                    if pr_result.get('pr_url'):
                        self.notify_service.send_notification(
                            event=event,
                            pr_url=pr_result.get('pr_url'),
                            repair_result=repair_result
                        )
                
                results.append(repair_result)
            
            return {
                "status": "SUCCESS",
                "results": results
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "message": str(e)
            }
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
