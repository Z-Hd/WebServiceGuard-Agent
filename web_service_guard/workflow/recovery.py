import time
from web_service_guard.delivery.pr_service import PRService
from web_service_guard.delivery.notify_service import NotifyService

class RecoveryService:
    """恢复服务"""
    
    def __init__(self):
        self.pr_service = PRService()
        self.notify_service = NotifyService()
        self.retry_interval = 5  # 重试间隔（秒）
        self.max_retries = 3  # 最大重试次数
    
    def recover_pr_creation(self, event, repair_result):
        """恢复PR创建"""
        for retry in range(self.max_retries):
            try:
                result = self.pr_service.create_pr(event, repair_result)
                if result.get('pr_url'):
                    return result
                time.sleep(self.retry_interval)
            except Exception as e:
                print(f"PR创建失败，正在重试 ({retry + 1}/{self.max_retries}): {e}")
                time.sleep(self.retry_interval)
        
        return {
            "status": "FAILED",
            "message": "PR创建失败，已达到最大重试次数"
        }
    
    def recover_notification(self, event, pr_url, repair_result):
        """恢复通知发送"""
        for retry in range(self.max_retries):
            try:
                result = self.notify_service.send_notification(event, pr_url, repair_result)
                if result.get('delivered'):
                    return result
                time.sleep(self.retry_interval)
            except Exception as e:
                print(f"通知发送失败，正在重试 ({retry + 1}/{self.max_retries}): {e}")
                time.sleep(self.retry_interval)
        
        return {
            "status": "FAILED",
            "message": "通知发送失败，已达到最大重试次数"
        }
    
    def recover_from_failure(self, run_id, failure_reason):
        """从失败中恢复"""
        # 记录失败原因
        print(f"运行 {run_id} 失败，原因: {failure_reason}")
        
        # 这里可以添加更多恢复逻辑，例如：
        # 1. 清理临时文件
        # 2. 回滚代码修改
        # 3. 发送失败通知
        
        return {
            "status": "RECOVERED",
            "message": f"已从失败中恢复，失败原因: {failure_reason}"
        }