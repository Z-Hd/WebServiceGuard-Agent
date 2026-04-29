from web_service_guard.agent_tools.base import AgentTool
from web_service_guard.primitive_tools.read_code import ReadCode
from web_service_guard.schemas.context import RepairContext
import re

class ExploreAgentTool(AgentTool):
    """探索AgentTool"""
    
    def invoke(self, payload: dict) -> dict:
        """调用探索AgentTool"""
        try:
            run_id = payload.get('run_id')
            iteration = payload.get('iteration', 0)
            input_data = payload.get('input', {})
            
            traceback = input_data.get('traceback')
            service = input_data.get('service')

            if not isinstance(traceback, str) or not traceback.strip():
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    agent_tool="ExploreAgentTool",
                    summary="缺少有效 Traceback",
                    output={},
                    artifacts=[],
                    errors=[{"code": "EXPLORE_TRACEBACK_INSUFFICIENT", "message": "缺少有效 Traceback", "retryable": False, "source": "ExploreAgentTool"}],
                    input_data=input_data,
                    next_recommendation="need_human_review",
                )
            
            # 解析Traceback，提取可疑文件
            suspect_files = self._extract_suspect_files(traceback)
            code_snippets = []
            related_tests = []
            recent_commits = []
            
            # 读取相关代码文件
            read_code_tool = ReadCode()
            for file_path in suspect_files:
                result = read_code_tool.execute(
                    run_id=run_id,
                    iteration=iteration,
                    input_data={"file": file_path, "include_related_tests": True},
                    constraints={"read_only": True, "invoked_by": "ExploreAgentTool"}
                )
                
                if result.get('status') == 'SUCCESS':
                    output = result.get('output', {})
                    code_snippets.append({
                        "file": file_path,
                        "content": output.get('content', ''),
                        "related_tests": output.get('related_tests', [])
                    })
                    related_tests.extend(output.get('related_tests', []))
            
            # 构建修复上下文
            repair_context = RepairContext(
                bug_summary=f"Error in {service}",
                traceback=traceback,
                suspect_files=suspect_files,
                code_snippets=code_snippets,
                related_tests=list(set(related_tests)),  # 去重
                recent_commits=recent_commits
            )
            
            # 评估上下文完整度
            context_completeness = "sufficient" if suspect_files and code_snippets else "insufficient"
            next_recommendation = "plan" if context_completeness == "sufficient" else "need_human_review"
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                agent_tool="ExploreAgentTool",
                summary=f"成功探索上下文，找到 {len(suspect_files)} 个可疑文件",
                output={
                    "repair_context": repair_context.to_dict(),
                    "suspect_files": suspect_files,
                    "related_tests": list(set(related_tests)),
                    "context_completeness": context_completeness
                },
                artifacts=suspect_files,
                errors=[],
                input_data=input_data,
                next_recommendation=next_recommendation,
            )
        except Exception as e:
            return self._create_result(
                run_id=payload.get('run_id'),
                iteration=payload.get('iteration', 0),
                agent_tool="ExploreAgentTool",
                summary="探索失败",
                output={},
                artifacts=[],
                errors=[{"code": "AGENT_EXPLORE_FAILED", "message": str(e), "retryable": True, "source": "ExploreAgentTool"}],
                input_data=payload.get('input', {}),
                next_recommendation="retry",
            )
    
    def _extract_suspect_files(self, traceback):
        """从Traceback中提取可疑文件"""
        suspect_files = []
        # 匹配File "path", line X 格式
        matches = re.findall(r'File "(.*?)", line \d+', traceback)
        for file_path in matches:
            if file_path not in suspect_files:
                suspect_files.append(file_path)
        return suspect_files
