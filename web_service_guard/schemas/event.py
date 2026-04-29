from typing import Optional, List

class BugEvent:
    """Bug事件"""
    def __init__(self, service: str, error_summary: str, traceback: str, timestamp: str, repo: str, branch: str):
        self.service = service
        self.error_summary = error_summary
        self.traceback = traceback
        self.timestamp = timestamp
        self.repo = repo
        self.branch = branch
    
    def to_dict(self):
        return {
            "service": self.service,
            "error_summary": self.error_summary,
            "traceback": self.traceback,
            "timestamp": self.timestamp,
            "repo": self.repo,
            "branch": self.branch
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            service=data.get('service'),
            error_summary=data.get('error_summary'),
            traceback=data.get('traceback'),
            timestamp=data.get('timestamp'),
            repo=data.get('repo'),
            branch=data.get('branch')
        )