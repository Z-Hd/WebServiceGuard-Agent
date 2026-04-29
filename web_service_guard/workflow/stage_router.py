from web_service_guard.enums import FinalStatus
from web_service_guard.policy import Policy

class StageRouter:
    """阶段路由器"""
    
    @staticmethod
    def should_proceed_to_repair(traceback, repo, branch):
        """判断是否应该进入修复阶段"""
        # 检查是否有有效Traceback
        if not traceback:
            return False, "无有效Traceback"
        
        # 检查是否能定位仓库和分支
        if not repo or not branch:
            return False, "无法定位仓库或分支"
        
        return True, "可以进入修复阶段"
    
    @staticmethod
    def should_proceed_to_pr(verification_result):
        """判断是否应该进入PR阶段"""
        return Policy.should_proceed_to_pr(verification_result)
    
    @staticmethod
    def should_escalate(risk_level, errors):
        """判断是否应该升级"""
        # 检查风险等级
        if risk_level and Policy.should_escalate_for_risk(risk_level):
            return True, "高风险操作"
        
        # 检查是否有不可重试的错误
        if errors:
            for error in errors:
                if not error.get('retryable'):
                    return True, "不可重试的错误"
        
        return False, "不需要升级"
    
    @staticmethod
    def route(repair_result):
        """根据修复结果路由到下一阶段"""
        final_status = repair_result.get('final_status')
        
        if final_status == FinalStatus.READY_FOR_PR.value:
            return "PR"
        elif final_status == FinalStatus.NEED_HUMAN_REVIEW.value:
            return "HUMAN_REVIEW"
        elif final_status == FinalStatus.FAILED.value:
            return "FAILED"
        else:
            return "UNKNOWN"