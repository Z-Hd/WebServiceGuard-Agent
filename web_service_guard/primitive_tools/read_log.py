import os
import re
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus

class ReadLog(PrimitiveTool):
    """读取日志工具"""
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行日志读取"""
        try:
            service = input_data.get('service')
            source = input_data.get('source')
            path = input_data.get('path')
            time_window = input_data.get('time_window')
            keyword = input_data.get('keyword')
            request_id = input_data.get('request_id')
            max_lines = input_data.get('max_lines', 1000)
            
            # 读取日志文件
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            else:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="日志文件不存在",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_READ_LOG_FAILED", "message": "日志文件不存在", "retryable": False, "source": "ReadLog"}]
                )
            
            # 过滤日志
            matched_lines = []
            traceback_blocks = []
            
            # 按关键字过滤
            if keyword:
                for line in lines:
                    if keyword in line:
                        matched_lines.append(line)
            else:
                matched_lines = lines
            
            # 提取Traceback
            i = 0
            while i < len(matched_lines):
                if 'Traceback (most recent call last):' in matched_lines[i]:
                    traceback = matched_lines[i]
                    i += 1
                    while i < len(matched_lines) and ('File' in matched_lines[i] or 'Exception' in matched_lines[i]):
                        traceback += matched_lines[i]
                        i += 1
                    traceback_blocks.append(traceback)
                else:
                    i += 1
            
            # 限制返回行数
            if max_lines and len(matched_lines) > max_lines:
                matched_lines = matched_lines[-max_lines:]
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.SUCCESS,
                summary=f"成功读取日志，找到 {len(traceback_blocks)} 个Traceback",
                output={
                    "traceback_blocks": traceback_blocks,
                    "matched_lines": len(matched_lines),
                    "source": source
                },
                artifacts=[path],
                errors=[]
            )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="读取日志失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_READ_LOG_FAILED", "message": str(e), "retryable": True, "source": "ReadLog"}]
            )