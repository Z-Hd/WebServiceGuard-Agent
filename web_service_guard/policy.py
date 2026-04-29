from web_service_guard.enums import RiskLevel

class Policy:
    """门禁与护栏规则"""
    
    @staticmethod
    def should_stop_for_risk(risk_level):
        """是否因风险停止"""
        return Policy._coerce_risk_level(risk_level) == RiskLevel.HIGH
    
    @staticmethod
    def should_escalate_for_risk(risk_level):
        """是否因风险升级"""
        return Policy._coerce_risk_level(risk_level) in [RiskLevel.MEDIUM, RiskLevel.HIGH]
    
    @staticmethod
    def should_continue_iteration(iteration, max_iterations):
        """是否继续迭代"""
        return iteration < max_iterations
    
    @staticmethod
    def should_proceed_to_pr(verification_result):
        """是否可以进入PR阶段"""
        return verification_result.get('targeted_tests_passed', False) and \
               verification_result.get('smoke_tests_passed', False)
    
    @staticmethod
    def is_high_risk_file(file_path):
        """判断是否为高风险文件"""
        high_risk_patterns = [
            'auth', 'authentication', 'security',
            'payment', 'billing', 'finance',
            'database', 'db', 'migration',
            'config', 'settings', 'secrets'
        ]
        file_path_lower = file_path.lower()
        return any(pattern in file_path_lower for pattern in high_risk_patterns)
    
    @staticmethod
    def is_high_risk_operation(operation):
        """判断是否为高风险操作"""
        high_risk_operations = [
            'delete', 'drop', 'remove',
            'truncate', 'alter', 'modify'
        ]
        operation_lower = operation.lower()
        return any(op in operation_lower for op in high_risk_operations)
    
    @staticmethod
    def validate_tool_access(tool_name, invoked_by):
        """验证工具访问权限"""
        # 写入工具必须由指定的AgentTool调用
        write_tools = ['EditCode', 'GitCommit', 'FeishuNotify']
        allowed_invokers = {
            'EditCode': ['ExecuteAgentTool'],
            'GitCommit': ['DeliveryAgent'],
            'FeishuNotify': ['DeliveryAgent']
        }
        
        if tool_name in write_tools:
            return invoked_by in allowed_invokers.get(tool_name, [])
        
        return True

    @staticmethod
    def _coerce_risk_level(risk_level):
        """兼容字符串和枚举两种风险等级表示。"""
        if isinstance(risk_level, RiskLevel):
            return risk_level

        if isinstance(risk_level, str):
            try:
                return RiskLevel(risk_level)
            except ValueError:
                return None

        return None
