import unittest
import os
import uuid
from web_service_guard.agent_tools.explore import ExploreAgentTool
from web_service_guard.agent_tools.plan import PlanAgentTool
from web_service_guard.agent_tools.execute import ExecuteAgentTool
from web_service_guard.agent_tools.verify import VerifyAgentTool

class TestAgentTools(unittest.TestCase):
    """测试AgentTool"""
    
    def setUp(self):
        self.explore_tool = ExploreAgentTool()
        self.plan_tool = PlanAgentTool()
        self.execute_tool = ExecuteAgentTool()
        self.verify_tool = VerifyAgentTool()
        self.temp_dir = None
        self.code_file = os.path.join(os.getcwd(), f"tmp_agent_tool_{uuid.uuid4().hex}.py")
        with open(self.code_file, "w", encoding="utf-8") as handle:
            handle.write("def divide(a, b):\n    return a / b\n")

    def tearDown(self):
        if os.path.exists(self.code_file):
            os.remove(self.code_file)
    
    def test_explore_tool(self):
        """测试探索工具"""
        test_payload = {
            "run_id": "test_run_1",
            "iteration": 1,
            "input": {
                "traceback": f"Traceback (most recent call last):\n  File \"{self.code_file}\", line 2, in divide\n    return a / b\nZeroDivisionError: division by zero",
                "service": "test_service",
                "repo": "test/repo",
                "branch": "main"
            },
            "constraints": {
                "max_turns": 5,
                "read_only": True,
                "allowed_tools": ["ReadLog", "ReadCode"]
            }
        }
        
        result = self.explore_tool.invoke(test_payload)
        self.assertIn('output', result)
        self.assertIn('repair_context', result['output'])
        self.assertEqual(result["output"]["context_completeness"], "sufficient")
    
    def test_plan_tool(self):
        """测试规划工具"""
        test_payload = {
            "run_id": "test_run_1",
            "iteration": 1,
            "input": {
                "repair_context": {
                    "bug_summary": "Error in test_service",
                    "traceback": f"Traceback (most recent call last):\n  File \"{self.code_file}\", line 2, in divide\n    return a / b\nZeroDivisionError: division by zero",
                    "suspect_files": [self.code_file],
                    "code_snippets": [],
                    "related_tests": [],
                    "recent_commits": []
                }
            },
            "constraints": {
                "max_turns": 5,
                "read_only": True
            }
        }
        
        result = self.plan_tool.invoke(test_payload)
        self.assertIn('output', result)
        self.assertIn('repair_plan', result['output'])
        self.assertEqual(result["next_recommendation"], "execute")

    def test_execute_tool(self):
        """测试执行工具会产出补丁结果。"""
        result = self.execute_tool.invoke(
            {
                "run_id": "test_run_1",
                "iteration": 1,
                "input": {
                    "repair_plan": {
                        "root_cause": "除零错误",
                        "fix_plan": ["添加除数为零的检查"],
                        "files_to_modify": [self.code_file],
                        "risk_level": "LOW",
                    }
                },
                "constraints": {"max_turns": 5, "read_only": False},
            }
        )

        self.assertEqual(result["next_recommendation"], "verify")
        self.assertEqual(result["output"]["patch_result"]["modified_files"], [self.code_file])

    def test_verify_tool_with_failing_test(self):
        """测试验证工具在任一测试失败时返回结构化失败。"""
        result = self.verify_tool.invoke(
            {
                "run_id": "test_run_1",
                "iteration": 1,
                "input": {
                    "modified_files": [self.code_file],
                    "tests_to_run": ['python -c "import sys; sys.exit(1)"'],
                    "smoke_tests": ['python -c "print(1)"'],
                },
                "constraints": {"max_turns": 5, "read_only": True},
            }
        )

        verification = result["output"]["verification_result"]
        self.assertFalse(verification["targeted_tests_passed"])
        self.assertFalse(verification["ready_for_pr"])
        self.assertTrue(result["errors"])

if __name__ == '__main__':
    unittest.main()
