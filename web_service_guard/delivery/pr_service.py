from web_service_guard.primitive_tools.git_commit import GitCommit
from web_service_guard.audit import audit_logger

class PRService:
    """PR服务"""
    
    def __init__(self):
        self.git_commit_tool = GitCommit()
    
    def create_pr(self, event, repair_result):
        """创建PR"""
        try:
            # 生成分支名
            branch_name = f"fix-{event.error_summary[:20].lower().replace(' ', '-')}"
            
            # 生成提交信息
            commit_message = f"Auto-fix: {event.error_summary}"
            pr_title = f"Auto-fix: {event.error_summary}"
            
            # 生成PR描述
            pr_body = f"## 自动修复

### 错误摘要
{event.error_summary}

### 根因说明
{repair_result.get('artifacts', {}).get('repair_plan', {}).get('root_cause', 'Unknown')}

### 修复说明
- 修改文件: {', '.join(repair_result.get('artifacts', {}).get('modified_files', []))}
- 修复轮次: {repair_result.get('iterations_used', 0)}

### 测试结果
- 定向测试: {'通过' if repair_result.get('artifacts', {}).get('verification_result', {}).get('targeted_tests_passed') else '失败'}
- 冒烟测试: {'通过' if repair_result.get('artifacts', {}).get('verification_result', {}).get('smoke_tests_passed') else '失败'}"
            
            # 执行Git操作
            result = self.git_commit_tool.execute(
                run_id=repair_result.get('run_id'),
                iteration=0,
                input_data={
                    "branch_name": branch_name,
                    "commit_message": commit_message,
                    "pr_title": pr_title,
                    "pr_body": pr_body
                },
                constraints={
                    "read_only": False
                }
            )
            
            if result.get('status') == 'SUCCESS':
                output = result.get('output', {})
                pr_url = output.get('pr_url')
                
                # 记录PR创建
                audit_logger.log_pr_created(
                    run_id=repair_result.get('run_id'),
                    pr_url=pr_url,
                    branch_name=branch_name,
                    commit_hash=output.get('commit_hash')
                )
                
                return {
                    "status": "SUCCESS",
                    "pr_url": pr_url,
                    "branch_name": branch_name
                }
            else:
                return {
                    "status": "FAILED",
                    "message": "PR创建失败"
                }
        except Exception as e:
            return {
                "status": "FAILED",
                "message": str(e)
            }