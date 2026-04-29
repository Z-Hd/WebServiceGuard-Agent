import os
import json
from datetime import datetime
from web_service_guard.enums import AuditEventType
from web_service_guard.config import config

class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self, storage_path=None):
        self.storage_path = storage_path or config.audit_storage_path
        os.makedirs(self.storage_path, exist_ok=True)
    
    def log(self, event_type, data):
        """记录审计事件"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type.value if isinstance(event_type, AuditEventType) else event_type,
            "data": data
        }
        
        # 按日期分文件存储
        date_str = datetime.now().strftime('%Y-%m-%d')
        file_path = os.path.join(self.storage_path, f"audit_{date_str}.jsonl")
        
        with open(file_path, 'a', encoding='utf-8') as f:
            json.dump(event, f, ensure_ascii=False)
            f.write('\n')
    
    def log_agent_tool_call(self, run_id, iteration, agent_tool, input_data, output_data):
        """记录AgentTool调用"""
        data = {
            "run_id": run_id,
            "iteration": iteration,
            "agent_tool": agent_tool,
            "input": input_data,
            "output": output_data
        }
        self.log(AuditEventType.AGENT_TOOL_CALL, data)
    
    def log_primitive_tool_call(self, run_id, iteration, tool_name, invoked_by, input_data, output_data):
        """记录PrimitiveTool调用"""
        data = {
            "run_id": run_id,
            "iteration": iteration,
            "tool_name": tool_name,
            "invoked_by": invoked_by,
            "input": input_data,
            "output": output_data
        }
        self.log(AuditEventType.PRIMITIVE_TOOL_CALL, data)
    
    def log_orchestrator_decision(self, run_id, iteration, decision, reason):
        """记录Orchestrator决策"""
        data = {
            "run_id": run_id,
            "iteration": iteration,
            "decision": decision,
            "reason": reason
        }
        self.log(AuditEventType.ORCHESTRATOR_DECISION, data)
    
    def log_fix_applied(self, run_id, modified_files, patch_summary):
        """记录修复应用"""
        data = {
            "run_id": run_id,
            "modified_files": modified_files,
            "patch_summary": patch_summary
        }
        self.log(AuditEventType.FIX_APPLIED, data)
    
    def log_test_executed(self, run_id, test_results):
        """记录测试执行"""
        data = {
            "run_id": run_id,
            "test_results": test_results
        }
        self.log(AuditEventType.TEST_EXECUTED, data)
    
    def log_pr_created(self, run_id, pr_url, branch_name, commit_hash):
        """记录PR创建"""
        data = {
            "run_id": run_id,
            "pr_url": pr_url,
            "branch_name": branch_name,
            "commit_hash": commit_hash
        }
        self.log(AuditEventType.PR_CREATED, data)
    
    def log_notification_sent(self, run_id, delivered, message_id, recipient):
        """记录通知发送"""
        data = {
            "run_id": run_id,
            "delivered": delivered,
            "message_id": message_id,
            "recipient": recipient
        }
        self.log(AuditEventType.NOTIFICATION_SENT, data)

# 创建全局审计日志记录器
audit_logger = AuditLogger()
