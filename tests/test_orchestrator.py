import unittest
from unittest.mock import Mock
from web_service_guard.runtime.orchestrator import RepairOrchestrator

class TestOrchestrator(unittest.TestCase):
    """测试修复编排器"""
    
    def setUp(self):
        self.orchestrator = RepairOrchestrator()
    
    def _task_input(self):
        return {
            "run_id": "test_run_1",
            "bug_event": {
                "service": "test_service",
                "error_summary": "ZeroDivisionError: division by zero",
                "traceback": "Traceback (most recent call last):\n  File \"test.py\", line 10, in <module>\n    result = 10 / 0\nZeroDivisionError: division by zero",
                "timestamp": "2026-04-26T16:00:00",
                "repo": "test/repo",
                "branch": "main"
            },
            "traceback": "Traceback (most recent call last):\n  File \"test.py\", line 10, in <module>\n    result = 10 / 0\nZeroDivisionError: division by zero",
            "repo": "test/repo",
            "branch": "main",
            "max_iterations": 3
        }

    def test_run_happy_path(self):
        """测试默认主路径能进入 READY_FOR_PR。"""
        self.orchestrator.explore_tool.invoke = Mock(
            return_value={
                "output": {
                    "repair_context": {
                        "bug_summary": "bug",
                        "traceback": "tb",
                        "suspect_files": ["a.py"],
                        "code_snippets": [{"file": "a.py", "content": "code", "related_tests": []}],
                        "related_tests": [],
                        "recent_commits": [],
                    },
                    "suspect_files": ["a.py"],
                    "related_tests": [],
                    "context_completeness": "sufficient",
                },
                "errors": [],
            }
        )
        self.orchestrator.plan_tool.invoke = Mock(
            return_value={
                "output": {
                    "root_cause_analysis": {"root_cause": "除零错误", "evidence": ["tb"], "risk_level": "LOW"},
                    "repair_plan": {"root_cause": "除零错误", "fix_plan": ["guard"], "files_to_modify": ["a.py"], "risk_level": "LOW"},
                    "tests_to_run": ["pytest tests/test_a.py"],
                },
                "errors": [],
                "next_recommendation": "execute",
            }
        )
        self.orchestrator.execute_tool.invoke = Mock(
            return_value={
                "output": {"patch_result": {"modified_files": ["a.py"], "patch_summary": ["patched"], "test_updates": []}},
                "errors": [],
                "next_recommendation": "verify",
            }
        )
        self.orchestrator.verify_tool.invoke = Mock(
            return_value={
                "output": {
                    "verification_result": {
                        "targeted_tests_passed": True,
                        "smoke_tests_passed": True,
                        "failed_tests": [],
                        "failure_logs": [],
                        "ready_for_pr": True,
                    }
                },
                "errors": [],
                "next_recommendation": "finish",
            }
        )

        result = self.orchestrator.run(self._task_input())

        self.assertEqual(result["final_status"], "READY_FOR_PR")
        self.assertEqual(result["current_stage"], "READY_FOR_PR")
        self.assertEqual(result["iterations_used"], 1)

    def test_run_stops_when_context_insufficient(self):
        """测试上下文不足时直接转人工。"""
        self.orchestrator.explore_tool.invoke = Mock(
            return_value={
                "output": {
                    "repair_context": {
                        "bug_summary": "bug",
                        "traceback": "tb",
                        "suspect_files": [],
                        "code_snippets": [],
                        "related_tests": [],
                        "recent_commits": [],
                    },
                    "suspect_files": [],
                    "related_tests": [],
                    "context_completeness": "insufficient",
                },
                "errors": [],
            }
        )

        result = self.orchestrator.run(self._task_input())

        self.assertEqual(result["final_status"], "NEED_HUMAN_REVIEW")
        self.assertEqual(result["current_stage"], "NEED_HUMAN_REVIEW")

    def test_run_retries_until_max_iterations(self):
        """测试验证持续失败时会重试直到最大轮次后转人工。"""
        self.orchestrator.explore_tool.invoke = Mock(
            return_value={
                "output": {
                    "repair_context": {
                        "bug_summary": "bug",
                        "traceback": "tb",
                        "suspect_files": ["a.py"],
                        "code_snippets": [{"file": "a.py", "content": "code", "related_tests": []}],
                        "related_tests": [],
                        "recent_commits": [],
                    },
                    "suspect_files": ["a.py"],
                    "related_tests": [],
                    "context_completeness": "sufficient",
                },
                "errors": [],
            }
        )
        self.orchestrator.plan_tool.invoke = Mock(
            return_value={
                "output": {
                    "root_cause_analysis": {"root_cause": "除零错误", "evidence": ["tb"], "risk_level": "LOW"},
                    "repair_plan": {"root_cause": "除零错误", "fix_plan": ["guard"], "files_to_modify": ["a.py"], "risk_level": "LOW"},
                    "tests_to_run": ["pytest tests/test_a.py"],
                },
                "errors": [],
                "next_recommendation": "execute",
            }
        )
        self.orchestrator.execute_tool.invoke = Mock(
            return_value={
                "output": {"patch_result": {"modified_files": ["a.py"], "patch_summary": ["patched"], "test_updates": []}},
                "errors": [],
                "next_recommendation": "verify",
            }
        )
        self.orchestrator.verify_tool.invoke = Mock(
            return_value={
                "output": {
                    "verification_result": {
                        "targeted_tests_passed": False,
                        "smoke_tests_passed": True,
                        "failed_tests": ["pytest tests/test_a.py"],
                        "failure_logs": ["failed"],
                        "ready_for_pr": False,
                    }
                },
                "errors": [{"code": "VERIFY_TARGETED_TEST_FAILED", "message": "定向测试失败", "retryable": False, "source": "VerifyAgentTool"}],
                "next_recommendation": "retry",
            }
        )

        result = self.orchestrator.run(self._task_input())

        self.assertEqual(result["final_status"], "NEED_HUMAN_REVIEW")
        self.assertEqual(result["current_stage"], "MAX_ITERATIONS_EXCEEDED")
        self.assertEqual(result["iterations_used"], 3)

if __name__ == '__main__':
    unittest.main()
