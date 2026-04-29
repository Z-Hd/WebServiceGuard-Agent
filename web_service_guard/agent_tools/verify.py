from web_service_guard.agent_tools.base import AgentTool
from web_service_guard.primitive_tools.run_test import RunTest
from web_service_guard.audit import audit_logger

class VerifyAgentTool(AgentTool):
    """验证AgentTool"""
    
    def invoke(self, payload: dict) -> dict:
        """调用验证AgentTool"""
        try:
            run_id = payload.get('run_id')
            iteration = payload.get('iteration', 0)
            input_data = payload.get('input', {})
            
            tests_to_run = input_data.get('tests_to_run', [])
            smoke_tests = input_data.get('smoke_tests', ['pytest', 'python -m unittest'])
            
            run_test_tool = RunTest()
            targeted_tests_passed, targeted_failed_tests, targeted_logs = self._run_commands(
                run_test_tool=run_test_tool,
                run_id=run_id,
                iteration=iteration,
                commands=tests_to_run,
                default_passed=True,
            )
            smoke_tests_passed, smoke_failed_tests, smoke_logs = self._run_commands(
                run_test_tool=run_test_tool,
                run_id=run_id,
                iteration=iteration,
                commands=smoke_tests,
                default_passed=True,
            )
            failed_tests = targeted_failed_tests + smoke_failed_tests
            failure_logs = targeted_logs + smoke_logs
            
            # 判断是否可以进入PR阶段
            ready_for_pr = targeted_tests_passed and smoke_tests_passed
            
            # 记录测试执行
            test_results = {
                "targeted_tests_passed": targeted_tests_passed,
                "smoke_tests_passed": smoke_tests_passed,
                "failed_tests": failed_tests
            }
            audit_logger.log_test_executed(run_id, test_results)
            if targeted_tests_passed and smoke_tests_passed:
                errors = []
            elif not targeted_tests_passed:
                errors = [{"code": "VERIFY_TARGETED_TEST_FAILED", "message": "定向测试失败", "retryable": False, "source": "VerifyAgentTool"}]
            else:
                errors = [{"code": "VERIFY_SMOKE_TEST_FAILED", "message": "冒烟测试失败", "retryable": False, "source": "VerifyAgentTool"}]
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                agent_tool="VerifyAgentTool",
                summary=f"测试{'通过' if ready_for_pr else '失败'}",
                output={
                    "verification_result": {
                        "targeted_tests_passed": targeted_tests_passed,
                        "smoke_tests_passed": smoke_tests_passed,
                        "failed_tests": failed_tests,
                        "failure_logs": failure_logs,
                        "ready_for_pr": ready_for_pr
                    }
                },
                artifacts=[],
                errors=errors,
                input_data=input_data,
                next_recommendation="finish" if ready_for_pr else "retry",
            )
        except Exception as e:
            return self._create_result(
                run_id=payload.get('run_id'),
                iteration=payload.get('iteration', 0),
                agent_tool="VerifyAgentTool",
                summary="验证失败",
                output={},
                artifacts=[],
                errors=[{"code": "VERIFY_TEST_ENVIRONMENT_ERROR", "message": str(e), "retryable": True, "source": "VerifyAgentTool"}],
                input_data=payload.get('input', {}),
                next_recommendation="retry",
            )

    def _run_commands(self, run_test_tool, run_id, iteration, commands, default_passed):
        if not commands:
            return default_passed, [], []

        all_passed = True
        failed_tests = []
        failure_logs = []
        for command in commands:
            normalized_command = self._normalize_test_command(command)
            result = run_test_tool.execute(
                run_id=run_id,
                iteration=iteration,
                input_data={"command": normalized_command},
                constraints={"read_only": True, "invoked_by": "VerifyAgentTool"},
            )
            output = result.get("output", {})
            passed = result.get("status") == "SUCCESS" and output.get("passed", False)
            if not passed:
                all_passed = False
                failed_tests.extend(output.get("failed_tests", []) or [normalized_command])
                failure_logs.extend(output.get("log_excerpt", []))

        return all_passed, failed_tests, failure_logs

    def _normalize_test_command(self, command):
        if isinstance(command, str) and command.endswith(".py"):
            return f'pytest "{command}"'
        return command
