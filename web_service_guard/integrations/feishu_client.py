import requests
import json
from web_service_guard.config import config

class FeishuClient:
    """飞书客户端"""
    
    def __init__(self):
        self.app_id = config.feishu_app_id
        self.app_secret = config.feishu_app_secret
        self.access_token = None
    
    def get_access_token(self):
        """获取访问令牌"""
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
    
    def send_message(self, receive_id, receive_id_type, msg_type, content):
        """发送消息"""
        try:
            if not self.access_token:
                self.get_access_token()
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "content": content,
                "msg_type": msg_type
            }
            
            response = requests.post(url, headers=headers, json=payload)
            result = response.json()
            if result.get('code') == 0:
                return result.get('data', {})
            else:
                print(f"Error sending message: {result.get('msg')}")
                return None
        except Exception as e:
            print(f"Error sending message: {e}")
            return None