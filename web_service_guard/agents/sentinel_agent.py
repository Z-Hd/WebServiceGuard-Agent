from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.monitoring.event_detector import EventDetector

class SentinelAgent:
    """哨兵Agent"""
    
    def __init__(self):
        self.traceback_collector = TracebackCollector()
        self.event_detector = EventDetector()
    
    def detect_and_create_tasks(self, service, repo, branch):
        """检测异常并创建修复任务"""
        # 收集Traceback
        tracebacks = self.traceback_collector.collect_tracebacks()
        
        # 生成BugEvent
        events = self.event_detector.detect_events(tracebacks, service, repo, branch)
        
        # 生成修复任务
        tasks = []
        for event in events:
            task = {
                "run_id": f"repair_{event.timestamp}",
                "bug_event": event.to_dict(),
                "traceback": event.traceback,
                "repo": repo,
                "branch": branch,
                "max_iterations": 3
            }
            tasks.append(task)
        
        return tasks