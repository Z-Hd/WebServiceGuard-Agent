from web_service_guard.agent_tools.base import AgentTool
from web_service_guard.schemas.repair_plan import RepairPlan
from web_service_guard.enums import RiskLevel
from web_service_guard.policy import Policy

class PlanAgentTool(AgentTool):
    """规划AgentTool"""
    
    def invoke(self, payload: dict) -> dict:
        """调用规划AgentTool"""
        try:
            run_id = payload.get('run_id')
            iteration = payload.get('iteration', 0)
            input_data = payload.get('input', {})
            
            repair_context = input_data.get('repair_context', {})
            traceback = repair_context.get('traceback')
            suspect_files = repair_context.get('suspect_files', [])
            code_snippets = repair_context.get('code_snippets', [])

            if not traceback or not suspect_files:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    agent_tool="PlanAgentTool",
                    summary="上下文证据不足，无法形成修复计划",
                    output={},
                    artifacts=[],
                    errors=[{"code": "PLAN_INSUFFICIENT_EVIDENCE", "message": "缺少 traceback 或明确可疑文件", "retryable": False, "source": "PlanAgentTool"}],
                    input_data=input_data,
                    next_recommendation="need_human_review",
                )
            
            # 分析根因
            root_cause_analysis = self._analyze_root_cause(traceback, code_snippets)
            if root_cause_analysis is None:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    agent_tool="PlanAgentTool",
                    summary="根因不明确，无法生成可执行修复计划",
                    output={},
                    artifacts=suspect_files,
                    errors=[{"code": "PLAN_UNACTIONABLE_REPAIR_PLAN", "message": "根因分析未产出可执行计划", "retryable": False, "source": "PlanAgentTool"}],
                    input_data=input_data,
                    next_recommendation="need_human_review",
                )
            
            # 生成修复计划
            repair_plan = self._generate_repair_plan(root_cause_analysis, suspect_files)
            
            # 评估风险等级
            risk_level = self._assess_risk_level(repair_plan, suspect_files)
            repair_plan.risk_level = risk_level
            
            # 建议执行的测试
            tests_to_run = self._suggest_tests(repair_context.get('related_tests', []))
            
            # 构建输出
            output = {
                "root_cause_analysis": {
                    "root_cause": root_cause_analysis,
                    "evidence": [traceback[:500]],  # 截取部分Traceback作为证据
                    "risk_level": risk_level.value
                },
                "repair_plan": repair_plan.to_dict(),
                "tests_to_run": tests_to_run
            }
            
            # 生成下一个推荐动作
            next_recommendation = "execute" if risk_level != RiskLevel.HIGH else "need_human_review"
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                agent_tool="PlanAgentTool",
                summary="成功生成修复计划",
                output=output,
                artifacts=suspect_files,
                errors=[],
                input_data=input_data,
                next_recommendation=next_recommendation,
            )
        except Exception as e:
            return self._create_result(
                run_id=payload.get('run_id'),
                iteration=payload.get('iteration', 0),
                agent_tool="PlanAgentTool",
                summary="规划失败",
                output={},
                artifacts=[],
                errors=[{"code": "AGENT_PLAN_FAILED", "message": str(e), "retryable": True, "source": "PlanAgentTool"}],
                input_data=payload.get('input', {}),
                next_recommendation="retry",
            )
    
    def _analyze_root_cause(self, traceback, code_snippets):
        """分析根因"""
        if "ZeroDivisionError" in traceback:
            return "除零错误"
        if "IndexError" in traceback:
            return "索引越界错误"
        if "KeyError" in traceback:
            return "键不存在错误"
        if "ValueError" in traceback:
            return "值错误"
        return None
    
    def _generate_repair_plan(self, root_cause, suspect_files):
        """生成修复计划"""
        fix_plan = []
        
        if root_cause == "除零错误":
            fix_plan.append("添加除数为零的检查")
        elif root_cause == "索引越界错误":
            fix_plan.append("添加索引范围检查")
        elif root_cause == "键不存在错误":
            fix_plan.append("添加键存在性检查")
        elif root_cause == "值错误":
            fix_plan.append("添加值类型检查")
        else:
            fix_plan.append("根据错误信息进行修复")
        
        return RepairPlan(
            root_cause=root_cause,
            fix_plan=fix_plan,
            files_to_modify=suspect_files,
            risk_level=RiskLevel.LOW
        )
    
    def _assess_risk_level(self, repair_plan, suspect_files):
        """评估风险等级"""
        # 检查是否涉及高风险文件
        for file_path in suspect_files:
            if Policy.is_high_risk_file(file_path):
                return RiskLevel.HIGH
        
        # 检查修复计划中的操作
        for fix in repair_plan.fix_plan:
            if Policy.is_high_risk_operation(fix):
                return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def _suggest_tests(self, related_tests):
        """建议执行的测试"""
        # 优先执行相关测试
        if related_tests:
            return [self._normalize_test_command(test) for test in related_tests]
        return ["pytest", "python -m unittest"]

    def _normalize_test_command(self, test):
        if isinstance(test, str) and test.endswith(".py"):
            return f'pytest "{test}"'
        return test
