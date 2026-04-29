import requests
from web_service_guard.config import config

class HealthcheckAdapter:
    """健康检查适配器"""
    def __init__(self):
        self.healthcheck_urls = config.get('healthcheck_urls', [])
        self.timeout = config.get('healthcheck_timeout', 5)
    
    def check_health(self):
        """检查服务健康状态"""
        results = []
        for url in self.healthcheck_urls:
            try:
                response = requests.get(url, timeout=self.timeout)
                status = 'healthy' if response.status_code == 200 else 'unhealthy'
                results.append({
                    'url': url,
                    'status': status,
                    'status_code': response.status_code
                })
            except Exception as e:
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })
        return results
    
    def detect_health_issues(self):
        """检测健康问题"""
        results = self.check_health()
        issues = []
        for result in results:
            if result['status'] != 'healthy':
                issues.append(result)
        return issues