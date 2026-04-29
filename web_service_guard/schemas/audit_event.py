from typing import Dict, Any, Optional
from datetime import datetime
from web_service_guard.enums import AuditEventType

class AuditEvent:
    """审计事件"""
    def __init__(self, event_type: AuditEventType, data: Dict[str, Any], timestamp: Optional[datetime] = None):
        self.event_type = event_type
        self.data = data
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "data": self.data
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            event_type=AuditEventType(data.get('event_type')),
            data=data.get('data', {}),
            timestamp=datetime.fromisoformat(data.get('timestamp')) if data.get('timestamp') else None
        )
