from web_service_guard.enums import DecisionType, RiskLevel
from web_service_guard.policy import Policy

class DecisionHelper:
    """决策辅助器"""
    
    @staticmethod
    def should_continue(iteration, max_iterations, verification_result=None, risk_level=None):
        """判断是否应该继续"""
        # 检查是否达到最大迭代次数
        if not Policy.should_continue_iteration(iteration, max_iterations):
            return False
        
        # 检查风险等级
        if risk_level and Policy.should_stop_for_risk(risk_level):
            return False
        
        # 检查验证结果
        if verification_result and Policy.should_proceed_to_pr(verification_result):
            return False
        
        return True
    
    @staticmethod
    def make_decision(iteration, max_iterations, verification_result=None, risk_level=None, errors=None):
        """做出决策"""
        # 检查是否达到最大迭代次数
        if not Policy.should_continue_iteration(iteration, max_iterations):
            return DecisionType.TERMINATE
        
        # 检查风险等级
        if risk_level and Policy.should_stop_for_risk(risk_level):
            return DecisionType.ESCALATE
        
        # 检查验证结果
        if verification_result:
            if Policy.should_proceed_to_pr(verification_result):
                return DecisionType.TERMINATE
            else:
                return DecisionType.RETRY
        
        # 检查错误
        if errors:
            # 检查是否有可重试的错误
            for error in errors:
                if error.get('retryable'):
                    return DecisionType.RETRY
            # 不可重试的错误，升级
            return DecisionType.ESCALATE
        
        # 默认继续
        return DecisionType.CONTINUE
    
    @staticmethod
    def should_escalate(errors, risk_level):
        """判断是否应该升级"""
        # 检查风险等级
        if risk_level and Policy.should_escalate_for_risk(risk_level):
            return True
        
        # 检查是否有不可重试的错误
        if errors:
            for error in errors:
                if not error.get('retryable'):
                    return True
        
        return False