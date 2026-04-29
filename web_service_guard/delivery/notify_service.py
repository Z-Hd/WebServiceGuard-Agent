from web_service_guard.primitive_tools.feishu_notify import FeishuNotify
from web_service_guard.audit import audit_logger

class NotifyService:
    """通知服务"""
    
    def __init__(self):
        self.feishu_notify_tool = FeishuNotify()
    
    def send_notification(self, event, pr_url, repair_result):
        """发送通知"""
        try:
            # 构建通知内容
            body = {
                "service": event.service,
                "summary": event.error_summary,
                "root_cause": repair_result.get('artifacts', {}).get('repair_plan', {}).get('root_cause', 'Unknown'),
                "pr_url": pr_url
            }
            
            # 执行飞书通知
            result = self.feishu_notify_tool.execute(
                run_id=repair_result.get('run_id'),
                iteration=0,
                input_data={
                    "title": "Bug 自动修复通知",
                    "body": body
                },
                constraints={
                    "read_only": True
                }
            )
            
            if result.get('status') == 'SUCCESS':
                output = result.get('output', {})
                
                # 记录通知发送
                audit_logger.log_notification_sent(
                    run_id=repair_result.get('run_id'),
                    delivered=output.get('delivered'),
                    message_id=output.get('message_id'),
                    recipient=output.get('recipient')
                )
                
                return {
                    "status": "SUCCESS",
                    "delivered": output.get('delivered'),
                    "message_id": output.get('message_id')
                }
            else:
                return {
                    "status": "FAILED",
                    "message": "通知发送失败"
                }
        except Exception as e:
            return {
                "status": "FAILED",
                "message": str(e)
            }