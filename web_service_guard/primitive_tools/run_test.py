import subprocess
import os
import time
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus

class RunTest(PrimitiveTool):
    """运行测试工具"""
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行测试运行"""
        try:
            command = input_data.get('command')
            working_dir = input_data.get('working_dir', os.getcwd())
            timeout_sec = input_data.get('timeout_sec', constraints.get('timeout_sec', 60))
            test_scope = input_data.get('test_scope')
            invoked_by = constraints.get("invoked_by")
            
            if not command:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="缺少测试命令",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_RUN_TEST_FAILED", "message": "缺少测试命令", "retryable": False, "source": "RunTest"}],
                    input_data=input_data,
                    invoked_by=invoked_by,
                )
            
            # 执行测试命令
            start_time = time.time()
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=working_dir, 
                capture_output=True, 
                text=True, 
                timeout=timeout_sec
            )
            duration_sec = round(time.time() - start_time, 3)
            
            # 解析测试结果
            passed = result.returncode == 0
            failed_tests = []
            combined_lines = [line for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
            log_excerpt = combined_lines[-50:]
            
            # 简单的测试失败解析
            if not passed:
                for line in combined_lines:
                    if 'FAILED' in line or 'ERROR' in line or 'error' in line.lower():
                        failed_tests.append(line)
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.SUCCESS if passed else ToolStatus.FAILED,
                summary=f"测试{'通过' if passed else '失败'}",
                output={
                    "passed": passed,
                    "exit_code": result.returncode,
                    "failed_tests": failed_tests,
                    "log_excerpt": log_excerpt,
                    "duration_sec": duration_sec,
                    "test_scope": test_scope,
                },
                artifacts=[],
                errors=[] if passed else [{"code": "TOOL_RUN_TEST_FAILED", "message": "测试失败", "retryable": False, "source": "RunTest"}],
                input_data=input_data,
                invoked_by=invoked_by,
            )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="运行测试失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_RUN_TEST_FAILED", "message": str(e), "retryable": True, "source": "RunTest"}],
                input_data=input_data,
                invoked_by=constraints.get("invoked_by"),
            )
