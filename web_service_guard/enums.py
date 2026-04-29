from enum import Enum

class FinalStatus(Enum):
    """最终任务状态"""
    READY_FOR_PR = "READY_FOR_PR"
    NEED_HUMAN_REVIEW = "NEED_HUMAN_REVIEW"
    FAILED = "FAILED"

class ToolStatus(Enum):
    """工具执行状态"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"

class RiskLevel(Enum):
    """风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AuditEventType(Enum):
    """审计事件类型"""
    AGENT_TOOL_CALL = "AGENT_TOOL_CALL"
    PRIMITIVE_TOOL_CALL = "PRIMITIVE_TOOL_CALL"
    ORCHESTRATOR_DECISION = "ORCHESTRATOR_DECISION"
    FIX_APPLIED = "FIX_APPLIED"
    TEST_EXECUTED = "TEST_EXECUTED"
    PR_CREATED = "PR_CREATED"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"

class DecisionType(Enum):
    """决策类型"""
    CONTINUE = "continue"
    RETRY = "retry"
    ESCALATE = "escalate"
    TERMINATE = "terminate"

class AgentToolType(Enum):
    """AgentTool类型"""
    EXPLORE = "ExploreAgentTool"
    PLAN = "PlanAgentTool"
    EXECUTE = "ExecuteAgentTool"
    VERIFY = "VerifyAgentTool"

class PrimitiveToolType(Enum):
    """PrimitiveTool类型"""
    READ_LOG = "ReadLog"
    READ_CODE = "ReadCode"
    EDIT_CODE = "EditCode"
    RUN_TEST = "RunTest"
    GIT_COMMIT = "GitCommit"
    FEISHU_NOTIFY = "FeishuNotify"