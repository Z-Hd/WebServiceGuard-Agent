import os
import git
from github import Github
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus
from web_service_guard.config import config

class GitCommit(PrimitiveTool):
    """Git提交工具"""
    
    def __init__(self):
        self.repo_url = config.git_repo_url
        self.github_token = config.github_token
        self.branch_prefix = config.git_branch_prefix
        self.commit_message = config.git_commit_message
        self.pr_title = config.git_pr_title
        self.pr_body = config.git_pr_body
        self.repo = None
        self.github = None
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行Git提交和PR创建"""
        try:
            branch_name = input_data.get('branch_name')
            commit_message = input_data.get('commit_message')
            pr_title = input_data.get('pr_title')
            pr_body = input_data.get('pr_body')
            
            # 克隆仓库
            repo_path = self.clone_repo()
            if not repo_path:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="克隆仓库失败",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_GIT_COMMIT_FAILED", "message": "克隆仓库失败", "retryable": True, "source": "GitCommit"}]
                )
            
            # 创建分支
            if not self.create_branch(branch_name):
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="创建分支失败",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_GIT_COMMIT_FAILED", "message": "创建分支失败", "retryable": True, "source": "GitCommit"}]
                )
            
            # 提交修改
            if not self.commit_changes(commit_message):
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="提交修改失败",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_GIT_COMMIT_FAILED", "message": "提交修改失败", "retryable": True, "source": "GitCommit"}]
                )
            
            # 创建PR
            pr_url = self.create_pr(pr_title, pr_body)
            if not pr_url:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="创建PR失败",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_GIT_COMMIT_FAILED", "message": "创建PR失败", "retryable": True, "source": "GitCommit"}]
                )
            
            # 获取提交哈希
            commit_hash = self.repo.head.commit.hexsha
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.SUCCESS,
                summary="成功创建PR",
                output={
                    "branch_name": branch_name,
                    "commit_hash": commit_hash,
                    "pr_url": pr_url
                },
                artifacts=[repo_path],
                errors=[]
            )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="Git操作失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_GIT_COMMIT_FAILED", "message": str(e), "retryable": True, "source": "GitCommit"}]
            )
    
    def clone_repo(self):
        """克隆代码仓库"""
        try:
            # 提取仓库名称
            repo_name = self.repo_url.split('/')[-1].replace('.git', '')
            repo_path = os.path.join(os.getcwd(), repo_name)
            
            # 如果仓库已存在，更新它
            if os.path.exists(repo_path):
                self.repo = git.Repo(repo_path)
                self.repo.remotes.origin.pull()
            else:
                # 克隆仓库
                self.repo = git.Repo.clone_from(self.repo_url, repo_path)
            
            return repo_path
        except Exception as e:
            print(f"Error cloning repo: {e}")
            return None
    
    def create_branch(self, branch_name):
        """创建修复分支"""
        try:
            if not self.repo:
                self.clone_repo()
            
            # 切换到主分支
            self.repo.git.checkout('main')
            self.repo.remotes.origin.pull()
            
            # 创建并切换到新分支
            branch = self.repo.create_head(branch_name)
            branch.checkout()
            
            return branch_name
        except Exception as e:
            print(f"Error creating branch: {e}")
            return None
    
    def commit_changes(self, commit_message):
        """提交修改"""
        try:
            if not self.repo:
                self.clone_repo()
            
            # 添加所有修改
            self.repo.git.add('.')
            
            # 提交修改
            self.repo.git.commit('-m', commit_message)
            
            # 推送分支
            current_branch = self.repo.active_branch.name
            self.repo.remotes.origin.push(current_branch)
            
            return True
        except Exception as e:
            print(f"Error committing changes: {e}")
            return False
    
    def create_pr(self, pr_title, pr_body):
        """创建 PR"""
        try:
            if not self.github:
                self.github = Github(self.github_token)
            
            # 提取仓库所有者和名称
            repo_full_name = self.repo_url.split('github.com/')[-1].replace('.git', '')
            
            # 获取仓库
            repo = self.github.get_repo(repo_full_name)
            
            # 创建 PR
            current_branch = self.repo.active_branch.name
            pr = repo.create_pull(
                title=pr_title,
                body=pr_body,
                head=current_branch,
                base='main'
            )
            
            return pr.html_url
        except Exception as e:
            print(f"Error creating PR: {e}")
            return None