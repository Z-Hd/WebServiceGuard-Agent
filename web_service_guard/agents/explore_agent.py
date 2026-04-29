from web_service_guard.agent_tools.explore import ExploreAgentTool

class ExploreAgent:
    """探索Agent"""
    
    def __init__(self):
        self.explore_tool = ExploreAgentTool()
    
    def explore(self, run_id, iteration, traceback, service, repo, branch):
        """执行探索任务"""
        return self.explore_tool.invoke({
            "run_id": run_id,
            "iteration": iteration,
            "input": {
                "traceback": traceback,
                "service": service,
                "repo": repo,
                "branch": branch
            },
            "constraints": {
                "max_turns": 5,
                "read_only": True,
                "allowed_tools": ["ReadLog", "ReadCode"]
            }
        })