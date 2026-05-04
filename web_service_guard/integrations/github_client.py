from github import Github
from web_service_guard.config import config

class GitHubClient:
    """GitHub客户端"""
    
    def __init__(self):
        self.github_token = config.github_token
        self.github = None
    
    def get_github(self):
        """获取GitHub实例"""
        if not self.github:
            self.github = Github(self.github_token)
        return self.github
    
    def get_repo(self, repo_full_name):
        """获取仓库"""
        try:
            github = self.get_github()
            return github.get_repo(repo_full_name)
        except Exception as e:
            print(f"Error getting repo: {e}")
            return None
    
    def create_pr(self, repo_full_name, title, body, head, base):
        """创建PR"""
        try:
            repo = self.get_repo(repo_full_name)
            if repo:
                pr = repo.create_pull(
                    title=title,
                    body=body,
                    head=head,
                    base=base
                )
                return pr.html_url
            else:
                return None
        except Exception as e:
            print(f"Error creating PR: {e}")
            return None