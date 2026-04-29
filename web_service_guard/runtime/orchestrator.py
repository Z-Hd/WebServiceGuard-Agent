from web_service_guard.agent_tools.explore import ExploreAgentTool
from web_service_guard.agent_tools.plan import PlanAgentTool
from web_service_guard.agent_tools.execute import ExecuteAgentTool
from web_service_guard.agent_tools.verify import VerifyAgentTool
from web_service_guard.enums import FinalStatus
from web_service_guard.policy import Policy
from web_service_guard.audit import audit_logger
from web_service_guard.schemas.run_result import RunResult

class RepairOrchestrator:
    """修复编排器"""
    
    def __init__(self):
        self.explore_tool = ExploreAgentTool()
        self.plan_tool = PlanAgentTool()
        self.execute_tool = ExecuteAgentTool()
        self.verify_tool = VerifyAgentTool()
    
    def run(self, task_input: dict) -> dict:
        """同步运行入口"""
        run_id = task_input.get('run_id')
        bug_event = task_input.get('bug_event', {})
        traceback = task_input.get('traceback')
        repo = task_input.get('repo')
        branch = task_input.get('branch')
        max_iterations = task_input.get('max_iterations', 3)
        
        iteration = 0
        current_stage = "START"
        artifacts = {}
        errors = []

        if not run_id or not traceback:
            errors.append(
                {
                    "code": "ORCH_INVALID_INPUT",
                    "message": "缺少 run_id 或 traceback，无法进入第二阶段修复流程",
                    "retryable": False,
                    "source": "RepairOrchestrator",
                }
            )
            return RunResult(
                run_id=run_id or "unknown",
                final_status=FinalStatus.NEED_HUMAN_REVIEW,
                current_stage="NEED_HUMAN_REVIEW",
                iterations_used=iteration,
                summary="输入不完整，已转人工审核",
                artifacts=artifacts,
                errors=errors,
            ).to_dict()
        
        try:
            # 主循环
            while iteration < max_iterations:
                iteration += 1
                
                # 探索阶段
                if current_stage in ["START", "RETRY"]:
                    explore_result = self.explore_tool.invoke({
                        "run_id": run_id,
                        "iteration": iteration,
                        "input": {
                            "traceback": traceback,
                            "service": bug_event.get('service', 'unknown'),
                            "repo": repo,
                            "branch": branch
                        },
                        "constraints": {
                            "max_turns": 5,
                            "read_only": True,
                            "allowed_tools": ["ReadLog", "ReadCode"]
                        }
                    })
                    
                    if explore_result.get('errors'):
                        errors.extend(explore_result.get('errors', []))
                        current_stage = "NEED_HUMAN_REVIEW"
                        break
                    
                    explore_output = explore_result.get('output', {})
                    artifacts['repair_context'] = explore_output.get('repair_context')
                    artifacts['suspect_files'] = explore_output.get('suspect_files', [])
                    if explore_output.get("context_completeness") != "sufficient":
                        errors.append(
                            {
                                "code": "EXPLORE_CONTEXT_INSUFFICIENT",
                                "message": "探索阶段未拿到充分上下文，停止自动修复",
                                "retryable": False,
                                "source": "RepairOrchestrator",
                            }
                        )
                        current_stage = "NEED_HUMAN_REVIEW"
                        break
                    current_stage = "EXPLORED"
                
                # 规划阶段
                if current_stage == "EXPLORED":
                    plan_result = self.plan_tool.invoke({
                        "run_id": run_id,
                        "iteration": iteration,
                        "input": {
                            "repair_context": artifacts.get('repair_context')
                        },
                        "constraints": {
                            "max_turns": 5,
                            "read_only": True
                        }
                    })
                    
                    if plan_result.get('errors'):
                        errors.extend(plan_result.get('errors', []))
                        current_stage = "NEED_HUMAN_REVIEW"
                        break
                    
                    plan_output = plan_result.get('output', {})
                    artifacts['repair_plan'] = plan_output.get('repair_plan')
                    artifacts['tests_to_run'] = plan_output.get('tests_to_run', [])
                    artifacts['root_cause_analysis'] = plan_output.get('root_cause_analysis', {})
                    
                    # 检查风险等级
                    risk_level = artifacts['root_cause_analysis'].get('risk_level')
                    if plan_result.get("next_recommendation") == "need_human_review" or Policy.should_stop_for_risk(risk_level):
                        current_stage = "NEED_HUMAN_REVIEW"
                        break
                    
                    current_stage = "PLANNED"
                
                # 执行阶段
                if current_stage == "PLANNED":
                    execute_result = self.execute_tool.invoke({
                        "run_id": run_id,
                        "iteration": iteration,
                        "input": {
                            "repair_plan": artifacts.get('repair_plan')
                        },
                        "constraints": {
                            "max_turns": 5,
                            "read_only": False,
                            "allowed_tools": ["ReadCode", "EditCode"]
                        }
                    })
                    
                    if execute_result.get('errors'):
                        errors.extend(execute_result.get('errors', []))
                        current_stage = "RETRY" if execute_result.get("next_recommendation") == "retry" else "NEED_HUMAN_REVIEW"
                        if current_stage != "RETRY":
                            break
                        continue
                    
                    patch_result = execute_result.get('output', {}).get('patch_result', {})
                    artifacts['patch_result'] = patch_result
                    artifacts['modified_files'] = patch_result.get('modified_files', [])
                    current_stage = "EXECUTED"
                
                # 验证阶段
                if current_stage == "EXECUTED":
                    verify_result = self.verify_tool.invoke({
                        "run_id": run_id,
                        "iteration": iteration,
                        "input": {
                            "modified_files": artifacts.get('modified_files', []),
                            "tests_to_run": artifacts.get('tests_to_run', []),
                            "smoke_tests": ["pytest", "python -m unittest"]
                        },
                        "constraints": {
                            "max_turns": 5,
                            "read_only": True,
                            "allowed_tools": ["RunTest", "ReadLog"]
                        }
                    })
                    
                    verification_result = verify_result.get('output', {}).get('verification_result', {})
                    artifacts['verification_result'] = verification_result
                    if verification_result.get('ready_for_pr'):
                        current_stage = "READY_FOR_PR"
                        break
                    errors.extend(verify_result.get('errors', []))
                    current_stage = "RETRY"
            
            # 确定最终状态
            if current_stage == "READY_FOR_PR":
                final_status = FinalStatus.READY_FOR_PR
                summary = "修复成功，准备创建PR"
            elif current_stage == "NEED_HUMAN_REVIEW":
                final_status = FinalStatus.NEED_HUMAN_REVIEW
                summary = "需要人工审核"
            elif iteration >= max_iterations:
                final_status = FinalStatus.NEED_HUMAN_REVIEW
                current_stage = "MAX_ITERATIONS_EXCEEDED"
                summary = f"达到最大修复轮次 {max_iterations}，转人工处理"
                errors.append(
                    {
                        "code": "ORCH_MAX_ITERATIONS_EXCEEDED",
                        "message": f"达到最大修复轮次 {max_iterations}",
                        "retryable": False,
                        "source": "RepairOrchestrator",
                    }
                )
            else:
                final_status = FinalStatus.FAILED
                summary = "修复失败"
            
            # 记录决策
            audit_logger.log_orchestrator_decision(
                run_id=run_id,
                iteration=iteration,
                decision=current_stage,
                reason=summary
            )
            
            # 构建运行结果
            run_result = RunResult(
                run_id=run_id,
                final_status=final_status,
                current_stage=current_stage,
                iterations_used=iteration,
                summary=summary,
                artifacts=artifacts,
                errors=errors
            )
            
            return run_result.to_dict()
        except Exception as e:
            # 记录异常
            errors.append({"code": "UNKNOWN_ERROR", "message": str(e), "retryable": False, "source": "RepairOrchestrator"})
            
            # 构建失败结果
            run_result = RunResult(
                run_id=run_id,
                final_status=FinalStatus.FAILED,
                current_stage="FAILED",
                iterations_used=iteration,
                summary=f"修复过程中发生异常: {str(e)}",
                artifacts=artifacts,
                errors=errors
            )
            
            return run_result.to_dict()
