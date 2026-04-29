from web_service_guard.agent_tools.verify import VerifyAgentTool

class VerificationAgent:
    """验证Agent"""
    
    def __init__(self):
        self.verify_tool = VerifyAgentTool()
    
    def verify(self, run_id, iteration, modified_files, tests_to_run, smoke_tests):
        """执行验证任务"""
        return self.verify_tool.invoke({
            "run_id": run_id,
            "iteration": iteration,
            "input": {
                "modified_files": modified_files,
                "tests_to_run": tests_to_run,
                "smoke_tests": smoke_tests
            },
            "constraints": {
                "max_turns": 5,
                "read_only": True,
                "allowed_tools": ["RunTest", "ReadLog"]
            }
        })