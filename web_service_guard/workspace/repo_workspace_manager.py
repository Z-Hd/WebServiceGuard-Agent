"""Prepare and synchronize a local git workspace before automated repair."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from web_service_guard.config import config
from web_service_guard.errors import make_error
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repo_workspace import RepoWorkspaceRequest, RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


WORKSPACE_STAGE = "WORKSPACE"
WORKSPACE_SOURCE = "RepoWorkspaceManager"


class RepoWorkspaceManager:
    """Create or synchronize a local git workspace for one repair run."""

    def __init__(
        self,
        *,
        git_executable: str = "git",
        branch_prefix: str | None = None,
    ) -> None:
        self._git = git_executable
        self._branch_prefix = branch_prefix or config.default_repair_branch_prefix

    def prepare(self, request: RepoWorkspaceRequest) -> RepoWorkspaceResult:
        result = RepoWorkspaceResult(
            repo_url=request.repo_url,
            repo_root=request.repo_root,
            branch=request.branch,
            workspace_ready=False,
        )
        repo_root = Path(request.repo_root)
        try:
            if not repo_root.exists() or self._is_empty_directory(repo_root):
                if not request.allow_clone:
                    self._append_error(
                        result,
                        code="WORKSPACE_REPO_ROOT_MISSING",
                        message=f"Workspace path is not initialized: {request.repo_root}",
                    )
                    return result
                self._clone_repo(request, repo_root, result)
            elif not self._is_git_repo(repo_root):
                if not request.managed_workspace:
                    self._append_error(
                        result,
                        code="WORKSPACE_NOT_GIT_REPO",
                        message=f"Workspace path is not a git repository: {request.repo_root}",
                    )
                    return result
                self._rebuild_workspace(request, repo_root, result, reason="workspace is not a git repository")
            elif not self._origin_matches(request, repo_root):
                if not request.managed_workspace:
                    self._append_error(
                        result,
                        code="WORKSPACE_REMOTE_MISMATCH",
                        message="Workspace remote origin does not match the requested repository.",
                    )
                    return result
                self._rebuild_workspace(request, repo_root, result, reason="workspace remote does not match requested repository")

            self._synchronize_workspace(
                request,
                repo_root,
                result,
                allow_rebuild_on_dirty=request.managed_workspace,
            )
            if result.errors:
                return result

            result.current_branch = self._get_current_branch(repo_root)
            if request.create_repair_branch:
                repair_branch = request.repair_branch_name or self._build_repair_branch_name(
                    service=request.service,
                    run_id=request.run_id,
                )
                self._ensure_repair_branch(repo_root, repair_branch, result)
                if result.errors:
                    return result
                result.current_branch = repair_branch
                result.repair_branch = repair_branch
                result.clean_worktree = self._is_worktree_clean(repo_root)

            result.head_commit = self._get_head_commit(repo_root)
            result.workspace_ready = True
            return result
        except WorkspaceCommandError as exc:
            self._append_error(
                result,
                code=exc.code,
                message=exc.message,
            )
            return result

    def prepare_for_task(
        self,
        repair_task: RepairTask,
        *,
        create_repair_branch: bool = True,
        require_clean_worktree: bool = True,
    ) -> RepoWorkspaceResult:
        request = RepoWorkspaceRequest(
            repo_url=repair_task.bug_event.repo,
            repo_root=repair_task.repo_root,
            branch=repair_task.bug_event.branch,
            run_id=repair_task.run_id,
            service=repair_task.bug_event.service,
            create_repair_branch=create_repair_branch,
            require_clean_worktree=require_clean_worktree,
            managed_workspace=True,
            )
        return self.prepare(request)

    def prepare_prepared_task(
        self,
        repair_task: RepairTask,
        *,
        create_repair_branch: bool = True,
        require_clean_worktree: bool = True,
    ) -> PreparedRepairTask:
        workspace = self.prepare_for_task(
            repair_task,
            create_repair_branch=create_repair_branch,
            require_clean_worktree=require_clean_worktree,
        )
        return PreparedRepairTask(
            repair_task=repair_task,
            workspace=workspace,
        )

    def _synchronize_workspace(
        self,
        request: RepoWorkspaceRequest,
        repo_root: Path,
        result: RepoWorkspaceResult,
        *,
        allow_rebuild_on_dirty: bool,
    ) -> None:
        self._run_git(repo_root, result, "fetch", "origin")
        result.fetched = True
        self._ensure_branch_exists(repo_root, request.branch, result)
        if result.errors:
            return

        remote_branch = f"origin/{request.branch}"
        self._run_git(repo_root, result, "checkout", "-B", request.branch, remote_branch)
        self._run_git(repo_root, result, "reset", "--hard", remote_branch)
        self._run_git(repo_root, result, "clean", "-fd")
        result.synced_with_remote = True
        result.clean_worktree = self._is_worktree_clean(repo_root)

        if request.require_clean_worktree and not result.clean_worktree:
            if allow_rebuild_on_dirty and request.managed_workspace:
                self._rebuild_workspace(
                    request,
                    repo_root,
                    result,
                    reason="workspace remained dirty after reset/clean",
                )
                self._synchronize_workspace(
                    request,
                    Path(request.repo_root),
                    result,
                    allow_rebuild_on_dirty=False,
                )
                return
            self._append_error(
                result,
                code="WORKSPACE_DIRTY_AFTER_SYNC",
                message=(
                    "Workspace remained dirty after fetch, checkout, reset, and clean; "
                    "automated preparation could not produce a usable workspace."
                ),
            )

    def _clone_repo(
        self,
        request: RepoWorkspaceRequest,
        repo_root: Path,
        result: RepoWorkspaceResult,
    ) -> None:
        if repo_root.exists() and not self._is_empty_directory(repo_root):
            raise WorkspaceCommandError(
                code="WORKSPACE_CLONE_TARGET_EXISTS",
                message=f"Clone target already exists: {repo_root}",
            )
        repo_root.parent.mkdir(parents=True, exist_ok=True)
        self._run_command(
            None,
            result,
            self._git,
            "clone",
            request.repo_url,
            str(repo_root),
        )
        result.cloned = True

    def _origin_matches(self, request: RepoWorkspaceRequest, repo_root: Path) -> bool:
        origin_url = self._capture_git(repo_root, "remote", "get-url", "origin")
        normalized_actual = origin_url.strip().rstrip("/")
        normalized_expected = request.repo_url.strip().rstrip("/")
        return normalized_actual == normalized_expected

    def _ensure_branch_exists(
        self,
        repo_root: Path,
        branch: str,
        result: RepoWorkspaceResult,
    ) -> None:
        remote_branch = f"origin/{branch}"
        try:
            self._capture_git(repo_root, "rev-parse", "--verify", remote_branch)
        except WorkspaceCommandError:
            self._append_error(
                result,
                code="WORKSPACE_BRANCH_NOT_FOUND",
                message=f"Remote branch not found: {remote_branch}",
            )

    def _ensure_repair_branch(
        self,
        repo_root: Path,
        repair_branch: str,
        result: RepoWorkspaceResult,
    ) -> None:
        self._run_git(repo_root, result, "checkout", "-B", repair_branch)

    def _is_git_repo(self, repo_root: Path) -> bool:
        git_dir = repo_root / ".git"
        if git_dir.exists():
            return True
        try:
            output = self._capture_git(repo_root, "rev-parse", "--is-inside-work-tree")
        except WorkspaceCommandError:
            return False
        return output.strip() == "true"

    def _is_worktree_clean(self, repo_root: Path) -> bool:
        status = self._capture_git(repo_root, "status", "--short")
        return status.strip() == ""

    def _is_empty_directory(self, repo_root: Path) -> bool:
        return repo_root.exists() and repo_root.is_dir() and not any(repo_root.iterdir())

    def _rebuild_workspace(
        self,
        request: RepoWorkspaceRequest,
        repo_root: Path,
        result: RepoWorkspaceResult,
        *,
        reason: str,
    ) -> None:
        self._record_action(result, f"rebuild workspace: {reason}")
        self._remove_workspace(repo_root, result)
        self._clone_repo(request, repo_root, result)
        result.rebuilt = True

    def _remove_workspace(self, repo_root: Path, result: RepoWorkspaceResult) -> None:
        if repo_root.exists():
            self._record_action(result, f"remove workspace {repo_root}")
            if repo_root.is_dir():
                shutil.rmtree(repo_root)
            else:
                repo_root.unlink()

    def _get_current_branch(self, repo_root: Path) -> str | None:
        branch = self._capture_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        branch = branch.strip()
        return branch or None

    def _get_head_commit(self, repo_root: Path) -> str | None:
        commit = self._capture_git(repo_root, "rev-parse", "HEAD")
        commit = commit.strip()
        return commit or None

    def _build_repair_branch_name(self, *, service: str | None, run_id: str) -> str:
        service_part = _slugify(service or "service")
        run_part = _slugify(run_id)
        return f"{self._branch_prefix}/{service_part}/{run_part}"

    def _run_git(self, repo_root: Path, result: RepoWorkspaceResult, *args: str) -> None:
        self._run_command(repo_root, result, self._git, *args)

    def _run_command(
        self,
        repo_root: Path | None,
        result: RepoWorkspaceResult,
        *command: str,
    ) -> None:
        workdir = None if repo_root is None else str(repo_root)
        completed = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            shell=False,
        )
        action = " ".join(command)
        self._record_action(result, action)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            details = stderr or stdout or f"Command exited with code {completed.returncode}"
            raise WorkspaceCommandError(
                code="WORKSPACE_GIT_COMMAND_FAILED",
                message=f"{action} failed: {details}",
            )

    def _capture_git(self, repo_root: Path, *args: str) -> str:
        completed = subprocess.run(
            (self._git, *args),
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            shell=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            details = stderr or stdout or f"Command exited with code {completed.returncode}"
            raise WorkspaceCommandError(
                code="WORKSPACE_GIT_COMMAND_FAILED",
                message=f"{self._git} {' '.join(args)} failed: {details}",
            )
        return completed.stdout

    def _append_error(self, result: RepoWorkspaceResult, *, code: str, message: str) -> None:
        result.errors.append(
            make_error(
                code=code,
                message=message,
                retryable=False,
                stage=WORKSPACE_STAGE,
                source=WORKSPACE_SOURCE,
            )
        )

    def _record_action(self, result: RepoWorkspaceResult, action: str) -> None:
        result.actions.append(action)


class WorkspaceCommandError(RuntimeError):
    """Raised when a git command fails during workspace preparation."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace("\\", "-").replace("/", "-")
    slug = re.sub(r"[^a-z0-9._-]+", "-", lowered).strip("-")
    return slug or "value"
