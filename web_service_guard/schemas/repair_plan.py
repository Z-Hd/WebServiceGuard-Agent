from typing import List
from web_service_guard.enums import RiskLevel

class RepairPlan:
    """修复计划"""
    def __init__(self, root_cause: str, fix_plan: List[str], files_to_modify: List[str], risk_level: RiskLevel):
        self.root_cause = root_cause
        self.fix_plan = fix_plan
        self.files_to_modify = files_to_modify
        self.risk_level = risk_level
    
    def to_dict(self):
        return {
            "root_cause": self.root_cause,
            "fix_plan": self.fix_plan,
            "files_to_modify": self.files_to_modify,
            "risk_level": self.risk_level.value
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            root_cause=data.get('root_cause'),
            fix_plan=data.get('fix_plan', []),
            files_to_modify=data.get('files_to_modify', []),
            risk_level=RiskLevel(data.get('risk_level', 'LOW'))
        )
