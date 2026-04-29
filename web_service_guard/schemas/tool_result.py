from typing import List, Optional, Dict, Any
from web_service_guard.enums import ToolStatus

class ToolResult:
    """工具执行结果"""
    def __init__(self, run_id: str, iteration: int, tool_name: str, status: ToolStatus, summary: str, output: Dict[str, Any], artifacts: List[str], errors: List[Dict[str, Any]]):
        self.run_id = run_id
        self.iteration = iteration
        self.tool_name = tool_name
        self.status = status
        self.summary = summary
        self.output = output
        self.artifacts = artifacts
        self.errors = errors
    
    def to_dict(self):
        return {
            "run_id": self.run_id,
            "iteration": self.iteration,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "summary": self.summary,
            "output": self.output,
            "artifacts": self.artifacts,
            "errors": self.errors
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            run_id=data.get('run_id'),
            iteration=data.get('iteration', 0),
            tool_name=data.get('tool_name'),
            status=ToolStatus(data.get('status', 'FAILED')),
            summary=data.get('summary', ''),
            output=data.get('output', {}),
            artifacts=data.get('artifacts', []),
            errors=data.get('errors', [])
        )
