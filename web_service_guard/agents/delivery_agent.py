from web_service_guard.delivery.pr_service import PRService
from web_service_guard.delivery.notify_service import NotifyService

class DeliveryAgent:
    """交付Agent"""
    
    def __init__(self):
        self.pr_service = PRService()
        self.notify_service = NotifyService()
    
    def deliver(self, event, repair_result):
        """执行交付任务"""
        # 创建PR
        pr_result = self.pr_service.create_pr(event, repair_result)
        
        # 发送通知
        if pr_result.get('pr_url'):
            notify_result = self.notify_service.send_notification(event, pr_result.get('pr_url'), repair_result)
            return {
                "pr_result": pr_result,
                "notify_result": notify_result
            }
        else:
            return {
                "pr_result": pr_result,
                "notify_result": {"status": "SKIPPED", "message": "PR创建失败，跳过通知"}
            }