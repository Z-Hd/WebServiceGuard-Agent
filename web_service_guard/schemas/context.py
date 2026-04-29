from typing import List, Optional, Dict, Any

class RepairContext:
    """修复上下文"""
    def __init__(self, bug_summary: str, traceback: str, suspect_files: List[str], code_snippets: List[Dict[str, Any]], related_tests: List[str], recent_commits: List[str]):
        self.bug_summary = bug_summary
        self.traceback = traceback
        self.suspect_files = suspect_files
        self.code_snippets = code_snippets
        self.related_tests = related_tests
        self.recent_commits = recent_commits
    
    def to_dict(self):
        return {
            "bug_summary": self.bug_summary,
            "traceback": self.traceback,
            "suspect_files": self.suspect_files,
            "code_snippets": self.code_snippets,
            "related_tests": self.related_tests,
            "recent_commits": self.recent_commits
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            bug_summary=data.get('bug_summary'),
            traceback=data.get('traceback'),
            suspect_files=data.get('suspect_files', []),
            code_snippets=data.get('code_snippets', []),
            related_tests=data.get('related_tests', []),
            recent_commits=data.get('recent_commits', [])
        )