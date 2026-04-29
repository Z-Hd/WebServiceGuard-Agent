from abc import ABC, abstractmethod
from typing import Dict, Any, List
from web_service_guard.audit import audit_logger

class AgentTool(ABC):
    """AgentTool抽象基类"""
    
    @abstractmethod
    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用AgentTool"""
        pass
    
    def _create_result(
        self,
        run_id: str,
        iteration: int,
        agent_tool: str,
        summary: str,
        output: Dict[str, Any],
        artifacts: List[str],
        errors: List[Dict[str, Any]],
        input_data: Dict[str, Any] | None = None,
        next_recommendation: str | None = None,
    ) -> Dict[str, Any]:
        """创建AgentTool执行结果"""
        result = {
            "run_id": run_id,
            "iteration": iteration,
            "agent_tool": agent_tool,
            "summary": summary,
            "output": output,
            "artifacts": artifacts,
            "errors": errors
        }

        if next_recommendation is not None:
            result["next_recommendation"] = next_recommendation
        
        # 记录审计日志
        audit_logger.log_agent_tool_call(run_id, iteration, agent_tool, input_data or {}, result)
        
        return result
