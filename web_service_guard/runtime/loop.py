from web_service_guard.enums import DecisionType
from web_service_guard.policy import Policy

class RepairLoop:
    """修复循环"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
    
    def run_loop(self, task_input: dict):
        """运行修复循环"""
        max_iterations = task_input.get('max_iterations', 3)
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # 执行一轮修复
            result = self.orchestrator.run(task_input)
            
            # 检查结果
            final_status = result.get('final_status')
            if final_status in ['READY_FOR_PR', 'NEED_HUMAN_REVIEW', 'FAILED']:
                return result
            
            # 更新任务输入，准备下一轮
            task_input['iteration'] = iteration
        
        # 达到最大迭代次数
        return {
            "run_id": task_input.get('run_id'),
            "final_status": "FAILED",
            "current_stage": "MAX_ITERATIONS",
            "iterations_used": max_iterations,
            "summary": f"达到最大迭代次数 {max_iterations}",
            "artifacts": {},
            "errors": [{"code": "WORKFLOW_MAX_ITERATIONS", "message": f"达到最大迭代次数 {max_iterations}", "retryable": False, "source": "RepairLoop"}]
        }
    
    def decide_next_action(self, current_result: dict, iteration: int, max_iterations: int):
        """决定下一步动作"""
        # 检查是否达到最大迭代次数
        if not Policy.should_continue_iteration(iteration, max_iterations):
            return DecisionType.TERMINATE
        
        # 检查验证结果
        verification_result = current_result.get('artifacts', {}).get('verification_result', {})
        if verification_result.get('ready_for_pr'):
            return DecisionType.TERMINATE
        
        # 检查是否有错误
        if current_result.get('errors'):
            # 检查是否可以重试
            for error in current_result.get('errors', []):
                if error.get('retryable'):
                    return DecisionType.RETRY
            return DecisionType.ESCALATE
        
        # 默认继续
        return DecisionType.CONTINUE