import requests
import json
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus
from web_service_guard.config import config

class FeishuNotify(PrimitiveTool):
    """飞书通知工具"""
    
    def __init__(self):
        self.app_id = config.feishu_app_id
        self.app_secret = config.feishu_app_secret
        self.webhook_url = config.feishu_webhook_url
        self.retry_count = config.feishu_retry_count
        self.retry_interval = config.feishu_retry_interval
        self.access_token = None
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行飞书通知"""
        try:
            webhook_url = input_data.get('webhook_url', self.webhook_url)
            title = input_data.get('title', 'Bug 自动修复通知')
            body = input_data.get('body', {})
            
            # 构建卡片
            card = self.build_card(title, body)
            
            # 发送通知
            delivered, message_id = self.send_notification(webhook_url, card)
            
            if delivered:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.SUCCESS,
                    summary="飞书通知发送成功",
                    output={
                        "delivered": delivered,
                        "message_id": message_id,
                        "recipient": "开发者"
                    },
                    artifacts=[],
                    errors=[]
                )
            else:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="飞书通知发送失败",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_FEISHU_NOTIFY_FAILED", "message": "飞书通知发送失败", "retryable": True, "source": "FeishuNotify"}]
                )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="飞书通知失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_FEISHU_NOTIFY_FAILED", "message": str(e), "retryable": True, "source": "FeishuNotify"}]
            )
    
    def get_access_token(self):
        """获取飞书访问令牌"""
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal/"
            payload = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            response = requests.post(url, json=payload)
            result = response.json()
            if result.get('code') == 0:
                self.access_token = result.get('app_access_token')
                return self.access_token
            else:
                print(f"Error getting access token: {result.get('msg')}")
                return None
        except Exception as e:
            print(f"Error getting access token: {e}")
            return None
    
    def build_card(self, title, body):
        """构建飞书卡片消息"""
        card = {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**服务**: {body.get('service', 'Unknown')}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**摘要**: {body.get('summary', 'Unknown')}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**根因**: {body.get('root_cause', 'Unknown')}"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**修复 PR**: [{body.get('pr_url', 'Unknown')}]({body.get('pr_url', '#')})"
                    }
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "我发现了一个 Bug 并已为您修复，请 Review"
                    }
                }
            ]
        }
        return card
    
    def send_notification(self, webhook_url, card):
        """发送飞书通知"""
        try:
            # 如果提供了 webhook_url，使用 Incoming Webhook 方式发送
            if webhook_url:
                headers = {
                    "Content-Type": "application/json"
                }
                payload = {
                    "msg_type": "interactive",
                    "card": card
                }
                
                # 重试机制
                for i in range(self.retry_count):
                    response = requests.post(webhook_url, headers=headers, json=payload)
                    result = response.json()
                    if result.get('code') == 0:
                        print("Notification sent successfully")
                        return True, result.get('data', {}).get('message_id')
                    else:
                        print(f"Error sending notification: {result.get('msg')}")
                        if i < self.retry_count - 1:
                            import time
                            time.sleep(self.retry_interval)
                return False, None
            
            # 否则使用应用方式发送
            if not self.access_token:
                self.get_access_token()
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "receive_id_type": "chat_id",  # 可以根据实际情况修改
                "receive_id": "oc_xxxx",  # 需要替换为实际的聊天 ID
                "content": json.dumps(card),
                "msg_type": "interactive"
            }
            
            # 重试机制
            for i in range(self.retry_count):
                response = requests.post(url, headers=headers, json=payload)
                result = response.json()
                if result.get('code') == 0:
                    print("Notification sent successfully")
                    return True, result.get('data', {}).get('message_id')
                else:
                    print(f"Error sending notification: {result.get('msg')}")
                    if i < self.retry_count - 1:
                        import time
                        time.sleep(self.retry_interval)
            
            return False, None
        except Exception as e:
            print(f"Error sending notification: {e}")
            return False, None