import re
from web_service_guard.schemas.event import BugEvent
from datetime import datetime

class EventDetector:
    """事件检测器"""
    def __init__(self):
        pass
    
    def detect_events(self, tracebacks, service, repo, branch):
        """检测错误并生成BugEvent"""
        events = []
        for traceback in tracebacks:
            # 提取错误信息
            error_info = self.extract_error_info(traceback)
            if error_info:
                # 生成BugEvent
                event = BugEvent(
                    service=service,
                    error_summary=f"{error_info['error_type']}: {error_info['error_message'][:50]}",
                    traceback=traceback,
                    timestamp=datetime.now().isoformat(),
                    repo=repo,
                    branch=branch
                )
                events.append(event)
        return events
    
    def extract_error_info(self, error_log):
        """从错误日志中提取错误信息"""
        # 提取错误类型
        error_type_match = re.search(r'([A-Za-z]+)Error:', error_log)
        error_type = error_type_match.group(1) if error_type_match else 'Unknown'
        
        # 提取错误消息
        error_message_match = re.search(r'Error: (.*)', error_log)
        error_message = error_message_match.group(1) if error_message_match else error_log
        
        # 提取 Traceback
        traceback_match = re.search(r'Traceback \(most recent call last\):(.*?)(?=[A-Za-z]+Error:|$)', error_log, re.DOTALL)
        traceback = traceback_match.group(1) if traceback_match else ''
        
        # 提取文件和行号
        file_line_match = re.search(r'File "(.*?)", line (\d+)', traceback)
        file_path = file_line_match.group(1) if file_line_match else ''
        line_number = file_line_match.group(2) if file_line_match else ''
        
        return {
            'error_type': error_type,
            'error_message': error_message,
            'traceback': traceback,
            'file_path': file_path,
            'line_number': line_number
        }