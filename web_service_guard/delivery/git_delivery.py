"""Local git publishing helpers for the third-stage delivery flow."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GitPublishResult:
    """Structured result for publishing a repair branch."""

    created: bool
    branch_name: str
    commit_hash: str | None = None
    modified_files: list[str] | None = None
    diff_stat: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "branch_name": self.branch_name,
            "commit_hash": self.commit_hash,
            "modified_files": list(self.modified_files or []),
            "diff_stat": self.diff_stat,
            "error": self.error,
        }


class GitDelivery:
    """Prepare commit metadata, create a commit, and push the repair branch."""

    def __init__(
        self,
        *,
        git_executable: str = "git",
        author_name: str = "Web Service Guard",
        author_email: str = "web-service-guard@example.com",
    ) -> None:
        self._git = git_executable
        self._author_name = author_name
        self._author_email = author_email

    def publish(
        self,
        *,
        repo_root: str,
        branch_name: str,
        commit_message: str,
    ) -> GitPublishResult:
        repo_path = Path(repo_root)
        if not repo_path.exists():
            return GitPublishResult(
                created=False,
                branch_name=branch_name,
                error=f"Repository root does not exist: {repo_root}",
            )
        if not repo_path.is_dir():
            return GitPublishResult(
                created=False,
                branch_name=branch_name,
                error=f"Repository root is not a directory: {repo_root}",
            )

        try:
            self._capture(repo_path, "rev-parse", "--is-inside-work-tree")
            current_branch = self._capture(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
            if current_branch != branch_name:
                self._run(repo_path, "checkout", branch_name)

            status_output = self._capture(repo_path, "status", "--short")
            if not status_output.strip():
                return GitPublishResult(
                    created=False,
                    branch_name=branch_name,
                    error="No uncommitted changes are available for delivery.",
                )

            self._run(repo_path, "add", "--all")
            diff_stat = self._capture(repo_path, "diff", "--cached", "--stat")
            modified_files = [
                line.strip()
                for line in self._capture(repo_path, "diff", "--cached", "--name-only").splitlines()
                if line.strip()
            ]
            if not modified_files:
                return GitPublishResult(
                    created=False,
                    branch_name=branch_name,
                    error="No staged files were collected for the delivery commit.",
                )

            self._run(
                repo_path,
                "-c",
                f"user.name={self._author_name}",
                "-c",
                f"user.email={self._author_email}",
                "commit",
                "-m",
                commit_message,
            )
            commit_hash = self._capture(repo_path, "rev-parse", "HEAD").strip()
            self._run(repo_path, "push", "--set-upstream", "origin", branch_name)
            return GitPublishResult(
                created=True,
                branch_name=branch_name,
                commit_hash=commit_hash or None,
                modified_files=modified_files,
                diff_stat=diff_stat.strip(),
            )
        except _GitCommandError as exc:
            return GitPublishResult(
                created=False,
                branch_name=branch_name,
                error=str(exc),
            )

    def _run(self, repo_path: Path, *args: str) -> None:
        completed = subprocess.run(
            [self._git, *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            shell=False,
        )
        if completed.returncode != 0:
            raise _GitCommandError(_format_git_error(self._git, args, completed))

    def _capture(self, repo_path: Path, *args: str) -> str:
        completed = subprocess.run(
            [self._git, *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            shell=False,
        )
        if completed.returncode != 0:
            raise _GitCommandError(_format_git_error(self._git, args, completed))
        return completed.stdout


class _GitCommandError(RuntimeError):
    """Raised when a git subprocess fails during stage-three delivery."""


def _format_git_error(
    git_executable: str,
    args: tuple[str, ...],
    completed: subprocess.CompletedProcess[str],
) -> str:
    details = (completed.stderr or "").strip() or (completed.stdout or "").strip()
    if not details:
        details = f"Command exited with code {completed.returncode}."
    return f"{git_executable} {' '.join(args)} failed: {details}"
