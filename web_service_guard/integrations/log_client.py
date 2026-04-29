import requests
from web_service_guard.config import config

class LogClient:
    """日志客户端"""
    
    def __init__(self):
        self.log_api_url = config.get('log_api_url')
        self.api_key = config.get('log_api_key')
    
    def get_logs(self, service, time_window, keyword=None):
        """获取日志"""
        if not self.log_api_url:
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            params = {
                "service": service,
                "time_window": time_window
            }
            if keyword:
                params["keyword"] = keyword
            
            response = requests.get(self.log_api_url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json().get('logs', [])
            else:
                return []
        except Exception as e:
            print(f"Error getting logs: {e}")
            return []