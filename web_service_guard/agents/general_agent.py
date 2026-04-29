from web_service_guard.agent_tools.execute import ExecuteAgentTool

class GeneralAgent:
    """执行Agent"""
    
    def __init__(self):
        self.execute_tool = ExecuteAgentTool()
    
    def execute(self, run_id, iteration, repair_plan):
        """执行修复任务"""
        return self.execute_tool.invoke({
            "run_id": run_id,
            "iteration": iteration,
            "input": {
                "repair_plan": repair_plan
            },
            "constraints": {
                "max_turns": 5,
                "read_only": False,
                "allowed_tools": ["ReadCode", "EditCode"]
            }
        })