class BaseError(Exception):
    """基础错误类"""
    def __init__(self, code, message, retryable=False, source=None):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.source = source
        super().__init__(message)

class ToolError(BaseError):
    """工具错误"""
    pass

class AgentError(BaseError):
    """Agent错误"""
    pass

class WorkflowError(BaseError):
    """工作流错误"""
    pass

class ConfigurationError(BaseError):
    """配置错误"""
    pass

# 错误码定义
ERROR_CODES = {
    # 工具错误
    "TOOL_READ_LOG_FAILED": "读取日志失败",
    "TOOL_READ_CODE_FAILED": "读取代码失败",
    "TOOL_EDIT_CODE_FAILED": "修改代码失败",
    "TOOL_RUN_TEST_FAILED": "运行测试失败",
    "TOOL_GIT_COMMIT_FAILED": "Git提交失败",
    "TOOL_FEISHU_NOTIFY_FAILED": "飞书通知失败",
    
    # Agent错误
    "AGENT_EXPLORE_FAILED": "探索Agent失败",
    "AGENT_PLAN_FAILED": "规划Agent失败",
    "AGENT_EXECUTE_FAILED": "执行Agent失败",
    "AGENT_VERIFY_FAILED": "验证Agent失败",
    
    # 工作流错误
    "WORKFLOW_NO_TRACEBACK": "无有效Traceback",
    "WORKFLOW_NO_REPO": "无法定位仓库",
    "WORKFLOW_MAX_ITERATIONS": "达到最大迭代次数",
    "WORKFLOW_HIGH_RISK": "高风险操作",
    "WORKFLOW_TEST_FAILED": "测试失败",
    
    # 配置错误
    "CONFIG_MISSING": "配置缺失",
    "CONFIG_INVALID": "配置无效",
    
    # 其他错误
    "UNKNOWN_ERROR": "未知错误"
}