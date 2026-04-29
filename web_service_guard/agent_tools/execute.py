from web_service_guard.agent_tools.base import AgentTool
from web_service_guard.primitive_tools.edit_code import EditCode
from web_service_guard.primitive_tools.read_code import ReadCode
from web_service_guard.audit import audit_logger
import re

class ExecuteAgentTool(AgentTool):
    """执行AgentTool"""
    
    def invoke(self, payload: dict) -> dict:
        """调用执行AgentTool"""
        try:
            run_id = payload.get('run_id')
            iteration = payload.get('iteration', 0)
            input_data = payload.get('input', {})
            
            repair_plan = input_data.get('repair_plan', {})
            root_cause = repair_plan.get('root_cause')
            fix_plan = repair_plan.get('fix_plan', [])
            files_to_modify = repair_plan.get('files_to_modify', [])

            if not root_cause or not files_to_modify:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    agent_tool="ExecuteAgentTool",
                    summary="修复计划不可执行",
                    output={},
                    artifacts=[],
                    errors=[{"code": "EXECUTE_PLAN_DEVIATION", "message": "缺少根因或待修改文件", "retryable": False, "source": "ExecuteAgentTool"}],
                    input_data=input_data,
                    next_recommendation="need_human_review",
                )
            
            modified_files = []
            patch_summary = []
            test_updates = []
            execution_errors = []
            
            # 读取代码并应用修复
            edit_code_tool = EditCode()
            read_code_tool = ReadCode()
            
            for file_path in files_to_modify:
                # 读取代码
                read_result = read_code_tool.execute(
                    run_id=run_id,
                    iteration=iteration,
                    input_data={"file": file_path},
                    constraints={"read_only": True, "invoked_by": "ExecuteAgentTool"}
                )
                
                if read_result.get('status') != 'SUCCESS':
                    execution_errors.extend(read_result.get("errors", []))
                    continue

                code = read_result.get('output', {}).get('content', '')
                modified_code = self._generate_fixed_code(code, root_cause, fix_plan)
                if modified_code == code:
                    execution_errors.append(
                        {"code": "EXECUTE_PATCH_APPLY_FAILED", "message": f"未能为 {file_path} 生成补丁", "retryable": False, "source": "ExecuteAgentTool"}
                    )
                    continue

                edit_result = edit_code_tool.execute(
                    run_id=run_id,
                    iteration=iteration,
                    input_data={
                        "file": file_path,
                        "edit_type": "replace_content",
                        "patch": modified_code,
                        "reason": "; ".join(fix_plan) if fix_plan else root_cause,
                    },
                    constraints={"read_only": False, "invoked_by": "ExecuteAgentTool"}
                )
                
                if edit_result.get('status') == 'SUCCESS':
                    modified_files.append(file_path)
                    patch_summary.extend(edit_result.get('output', {}).get('diff_summary', []))
                else:
                    execution_errors.extend(edit_result.get("errors", []))

            if not modified_files:
                if not execution_errors:
                    execution_errors.append(
                        {"code": "EXECUTE_PATCH_APPLY_FAILED", "message": "没有任何补丁被成功应用", "retryable": False, "source": "ExecuteAgentTool"}
                    )
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    agent_tool="ExecuteAgentTool",
                    summary="未成功应用补丁",
                    output={},
                    artifacts=[],
                    errors=execution_errors,
                    input_data=input_data,
                    next_recommendation="retry",
                )
            
            # 记录修复应用
            audit_logger.log_fix_applied(run_id, modified_files, patch_summary)
            
            # 生成下一个推荐动作
            next_recommendation = "verify" if modified_files else "retry"
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                agent_tool="ExecuteAgentTool",
                summary=f"成功修改 {len(modified_files)} 个文件",
                output={
                    "patch_result": {
                        "modified_files": modified_files,
                        "patch_summary": patch_summary,
                        "test_updates": test_updates
                    }
                },
                artifacts=modified_files,
                errors=[],
                input_data=input_data,
                next_recommendation=next_recommendation,
            )
        except Exception as e:
            return self._create_result(
                run_id=payload.get('run_id'),
                iteration=payload.get('iteration', 0),
                agent_tool="ExecuteAgentTool",
                summary="执行失败",
                output={},
                artifacts=[],
                errors=[{"code": "AGENT_EXECUTE_FAILED", "message": str(e), "retryable": True, "source": "ExecuteAgentTool"}],
                input_data=payload.get('input', {}),
                next_recommendation="retry",
            )
    
    def _generate_fixed_code(self, code, root_cause, fix_plan):
        """根据根因生成修复代码"""
        if root_cause == "除零错误":
            return self._guard_division(code)
        if root_cause == "索引越界错误":
            return self._guard_index_access(code)
        if root_cause == "键不存在错误":
            return self._guard_key_access(code)
        return code

    def _guard_division(self, code):
        match = re.search(r"^(?P<indent>\s*)return\s+(?P<left>[\w\.]+)\s*/\s*(?P<right>[\w\.]+)\s*$", code, re.MULTILINE)
        if not match:
            return code

        indent = match.group("indent")
        left = match.group("left")
        right = match.group("right")
        replacement = (
            f"{indent}if {right} == 0:\n"
            f"{indent}    return 0\n"
            f"{indent}return {left} / {right}"
        )
        return code.replace(match.group(0), replacement, 1)

    def _guard_index_access(self, code):
        match = re.search(r"^(?P<indent>\s*)return\s+(?P<items>[\w\.]+)\[(?P<index>[^\]]+)\]\s*$", code, re.MULTILINE)
        if not match:
            return code

        indent = match.group("indent")
        items = match.group("items")
        index = match.group("index").strip()
        replacement = (
            f"{indent}if {index} < 0 or {index} >= len({items}):\n"
            f"{indent}    return None\n"
            f"{indent}return {items}[{index}]"
        )
        return code.replace(match.group(0), replacement, 1)

    def _guard_key_access(self, code):
        match = re.search(r"^(?P<indent>\s*)return\s+(?P<mapping>[\w\.]+)\[(?P<key>[^\]]+)\]\s*$", code, re.MULTILINE)
        if not match:
            return code

        indent = match.group("indent")
        mapping = match.group("mapping")
        key = match.group("key").strip()
        replacement = f"{indent}return {mapping}.get({key})"
        return code.replace(match.group(0), replacement, 1)
