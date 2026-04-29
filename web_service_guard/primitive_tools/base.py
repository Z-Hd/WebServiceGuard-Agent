from abc import ABC, abstractmethod
from typing import Dict, Any, List
from web_service_guard.audit import audit_logger
from web_service_guard.enums import ToolStatus

class PrimitiveTool(ABC):
    """PrimitiveTool抽象基类"""
    
    @abstractmethod
    def execute(self, run_id: str, iteration: int, input_data: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        pass
    
    def _create_result(
        self,
        run_id: str,
        iteration: int,
        status: ToolStatus,
        summary: str,
        output: Dict[str, Any],
        artifacts: List[str],
        errors: List[Dict[str, Any]],
        input_data: Dict[str, Any] | None = None,
        invoked_by: str | None = None,
    ) -> Dict[str, Any]:
        """创建工具执行结果"""
        result = {
            "run_id": run_id,
            "iteration": iteration,
            "tool_name": self.__class__.__name__,
            "status": status.value,
            "summary": summary,
            "output": output,
            "artifacts": artifacts,
            "errors": errors
        }

        audit_logger.log_primitive_tool_call(
            run_id=run_id,
            iteration=iteration,
            tool_name=self.__class__.__name__,
            invoked_by=invoked_by or "unknown",
            input_data=input_data or {},
            output_data=result,
        )

        return result
