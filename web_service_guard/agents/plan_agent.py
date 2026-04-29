from web_service_guard.agent_tools.plan import PlanAgentTool

class PlanAgent:
    """规划Agent"""
    
    def __init__(self):
        self.plan_tool = PlanAgentTool()
    
    def plan(self, run_id, iteration, repair_context):
        """执行规划任务"""
        return self.plan_tool.invoke({
            "run_id": run_id,
            "iteration": iteration,
            "input": {
                "repair_context": repair_context
            },
            "constraints": {
                "max_turns": 5,
                "read_only": True
            }
        })