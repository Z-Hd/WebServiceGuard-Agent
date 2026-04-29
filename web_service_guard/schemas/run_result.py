from typing import List, Optional, Dict, Any
from web_service_guard.enums import FinalStatus

class RunResult:
    """运行结果"""
    def __init__(self, run_id: str, final_status: FinalStatus, current_stage: str, iterations_used: int, summary: str, artifacts: Dict[str, Any], errors: List[Dict[str, Any]]):
        self.run_id = run_id
        self.final_status = final_status
        self.current_stage = current_stage
        self.iterations_used = iterations_used
        self.summary = summary
        self.artifacts = artifacts
        self.errors = errors
    
    def to_dict(self):
        return {
            "run_id": self.run_id,
            "final_status": self.final_status.value,
            "current_stage": self.current_stage,
            "iterations_used": self.iterations_used,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "errors": self.errors
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            run_id=data.get('run_id'),
            final_status=FinalStatus(data.get('final_status', 'FAILED')),
            current_stage=data.get('current_stage', ''),
            iterations_used=data.get('iterations_used', 0),
            summary=data.get('summary', ''),
            artifacts=data.get('artifacts', {}),
            errors=data.get('errors', [])
        )
