import os
import re
import time
from web_service_guard.config import config

class TracebackCollector:
    """Traceback收集器"""
    def __init__(self):
        self.log_path = config.log_path
        self.log_pattern = config.get('monitor_log_pattern')
        self.check_interval = config.get('monitor_check_interval', 10)
        self.max_log_size = config.get('monitor_max_log_size', 1048576)
        self.last_check_time = time.time()
    
    def collect_tracebacks(self):
        """收集日志文件中的错误信息和Traceback"""
        if not os.path.exists(self.log_path):
            return []
        
        tracebacks = []
        try:
            # 检查文件大小
            file_size = os.path.getsize(self.log_path)
            if file_size > self.max_log_size:
                # 如果文件太大，只读取最后一部分
                with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(max(0, file_size - self.max_log_size))
                    lines = f.readlines()
            else:
                # 读取整个文件
                with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
            
            # 提取完整的错误信息（包括 Traceback）
            i = 0
            while i < len(lines):
                if re.search(self.log_pattern, lines[i], re.IGNORECASE):
                    error = lines[i]
                    i += 1
                    # 收集 Traceback 信息
                    while i < len(lines) and ('Traceback' in lines[i] or 'File' in lines[i] or 'Exception' in lines[i]):
                        error += lines[i]
                        i += 1
                    tracebacks.append(error)
                else:
                    i += 1
        except Exception as e:
            print(f"Error collecting tracebacks: {e}")
        
        return tracebacks
    
    def check_new_errors(self):
        """检查是否有新的错误"""
        current_time = time.time()
        if current_time - self.last_check_time < self.check_interval:
            return []
        
        tracebacks = self.collect_tracebacks()
        self.last_check_time = current_time
        return tracebacks