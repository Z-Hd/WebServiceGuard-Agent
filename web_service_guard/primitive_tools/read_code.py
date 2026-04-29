import os
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus

class ReadCode(PrimitiveTool):
    """读取代码工具"""
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行代码读取"""
        try:
            file = input_data.get('file')
            start_line = input_data.get('start_line')
            end_line = input_data.get('end_line')
            include_related_tests = input_data.get('include_related_tests', False)
            invoked_by = constraints.get("invoked_by")
            
            # 读取代码文件
            if not file or not os.path.exists(file):
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="代码文件不存在",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_READ_CODE_FAILED", "message": "代码文件不存在", "retryable": False, "source": "ReadCode"}],
                    input_data=input_data,
                    invoked_by=invoked_by,
                )
            
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 提取指定范围的代码
            if start_line and end_line:
                content = ''.join(lines[start_line-1:end_line])
            elif start_line:
                content = ''.join(lines[start_line-1:])
            else:
                content = ''.join(lines)
            
            # 查找相关测试
            related_tests = []
            if include_related_tests:
                # 简单的测试文件查找逻辑
                test_dirs = ['tests', 'test']
                file_name = os.path.basename(file)
                test_file_pattern = f"test_{file_name}" if not file_name.startswith('test_') else file_name
                
                for test_dir in test_dirs:
                    if os.path.exists(test_dir):
                        for root, dirs, files in os.walk(test_dir):
                            for test_file in files:
                                if test_file_pattern in test_file:
                                    related_tests.append(os.path.join(root, test_file))
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.SUCCESS,
                summary=f"成功读取代码文件 {file}",
                output={
                    "file": file,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": content,
                    "related_tests": related_tests
                },
                artifacts=[file],
                errors=[],
                input_data=input_data,
                invoked_by=invoked_by,
            )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="读取代码失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_READ_CODE_FAILED", "message": str(e), "retryable": True, "source": "ReadCode"}],
                input_data=input_data,
                invoked_by=constraints.get("invoked_by"),
            )
