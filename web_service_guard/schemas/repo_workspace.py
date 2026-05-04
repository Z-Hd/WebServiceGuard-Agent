"""Schemas for preparing a local git workspace before repair begins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RepoWorkspaceRequest:
    """Describe how to prepare a local workspace for one repair run."""

    repo_url: str
    repo_root: str
    branch: str
    run_id: str
    service: str | None = None
    repair_branch_name: str | None = None
    allow_clone: bool = True
    require_clean_worktree: bool = True
    create_repair_branch: bool = True
    managed_workspace: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "run_id": self.run_id,
            "service": self.service,
            "repair_branch_name": self.repair_branch_name,
            "allow_clone": self.allow_clone,
            "require_clean_worktree": self.require_clean_worktree,
            "create_repair_branch": self.create_repair_branch,
            "managed_workspace": self.managed_workspace,
        }


@dataclass(slots=True)
class RepoWorkspaceResult:
    """Result returned after preparing a local git workspace."""

    repo_url: str
    repo_root: str
    branch: str
    workspace_ready: bool
    current_branch: str | None = None
    repair_branch: str | None = None
    head_commit: str | None = None
    cloned: bool = False
    rebuilt: bool = False
    fetched: bool = False
    clean_worktree: bool = False
    synced_with_remote: bool = False
    actions: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "workspace_ready": self.workspace_ready,
            "current_branch": self.current_branch,
            "repair_branch": self.repair_branch,
            "head_commit": self.head_commit,
            "cloned": self.cloned,
            "rebuilt": self.rebuilt,
            "fetched": self.fetched,
            "clean_worktree": self.clean_worktree,
            "synced_with_remote": self.synced_with_remote,
            "actions": list(self.actions),
            "errors": list(self.errors),
        }
