"""Tests for the third-stage delivery flow."""

from __future__ import annotations

import subprocess
from pathlib import Path

from web_service_guard.agents.sentinel_agent import _utc_now
from web_service_guard.delivery.notify_service import NotifyService
from web_service_guard.delivery.pr_service import PRService
from web_service_guard.delivery.service import DeliveryService
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repo_workspace import RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


class FakeGitHubClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict[str, object]] = []

    def create_pull_request(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.should_fail:
            return {"created": False, "error": "github failed"}
        return {"created": True, "url": "https://github.com/acme/service/pull/1", "number": 1}


class FakeFeishuClient:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.payloads: list[dict[str, object]] = []

    def send_webhook(self, payload):
        self.payloads.append(dict(payload))
        if self.should_fail:
            return {"sent": False, "error": "feishu failed"}
        return {"sent": True, "status_code": 200, "raw": {"code": 0}}


def test_delivery_service_skips_when_gate_fails(tmp_path: Path) -> None:
    prepared_task = make_prepared_task(tmp_path, workspace_ready=False)
    service = DeliveryService()

    result = service.run(
        prepared_task=prepared_task,
        repair_result=make_repair_result(final_status="NEED_HUMAN_REVIEW"),
    )

    assert result["status"] == "SKIPPED"
    assert result["gate_passed"] is False
    assert result["errors"]


def test_delivery_service_publishes_pr_and_notification(tmp_path: Path) -> None:
    repo_root, branch_name = create_publishable_repo(tmp_path)
    prepared_task = make_prepared_task(repo_root, repair_branch=branch_name)
    service = DeliveryService(
        pr_service=PRService(github_client=FakeGitHubClient()),
        notify_service=NotifyService(feishu_client=FakeFeishuClient()),
    )

    result = service.run(
        prepared_task=prepared_task,
        repair_result=make_repair_result(),
    )

    assert result["status"] == "SUCCESS"
    assert result["gate_passed"] is True
    assert result["commit"]["created"] is True
    assert result["pr"]["created"] is True
    assert result["notification"]["sent"] is True


def test_delivery_service_returns_partial_when_notification_fails(tmp_path: Path) -> None:
    repo_root, branch_name = create_publishable_repo(tmp_path)
    prepared_task = make_prepared_task(repo_root, repair_branch=branch_name)
    service = DeliveryService(
        pr_service=PRService(github_client=FakeGitHubClient()),
        notify_service=NotifyService(feishu_client=FakeFeishuClient(should_fail=True)),
    )

    result = service.run(
        prepared_task=prepared_task,
        repair_result=make_repair_result(),
    )

    assert result["status"] == "PARTIAL"
    assert result["pr"]["created"] is True
    assert result["notification"]["sent"] is False
    assert result["errors"][0]["code"] == "DELIVERY_NOTIFY_FAILED"


def make_prepared_task(
    repo_root: Path,
    *,
    workspace_ready: bool = True,
    repair_branch: str = "autofix/demo/run-001",
) -> PreparedRepairTask:
    bug_event = BugEvent(
        event_id="evt-001",
        source="log",
        service="demo-service",
        repo="acme/demo-service",
        branch="main",
        detected_at=_utc_now(),
        error_type="ValueError",
        error_message="bad value",
        error_summary="ValueError: bad value",
        traceback="Traceback (most recent call last): ...",
        fingerprint="abc12345",
    )
    repair_task = RepairTask(
        run_id="run-001",
        bug_event=bug_event,
        repo_root=str(repo_root),
        max_iterations=2,
        created_at=_utc_now(),
    )
    workspace = RepoWorkspaceResult(
        repo_url=bug_event.repo,
        repo_root=str(repo_root),
        branch="main",
        workspace_ready=workspace_ready,
        current_branch=repair_branch,
        repair_branch=repair_branch,
        head_commit="HEAD",
        clean_worktree=False,
        synced_with_remote=True,
    )
    return PreparedRepairTask(repair_task=repair_task, workspace=workspace)


def make_repair_result(*, final_status: str = "READY_FOR_PR") -> dict[str, object]:
    return {
        "run_id": "run-001",
        "final_status": final_status,
        "current_stage": final_status,
        "iterations_used": 1,
        "summary": "VERDICT: PASS",
        "artifacts": {
            "plan": {
                "output": {
                    "root_cause_analysis": {
                        "root_cause": "Missing null guard",
                        "evidence": ["Traceback points to handler"],
                        "risk_level": "medium",
                    },
                    "repair_plan": {
                        "root_cause": "Missing null guard",
                        "fix_plan": ["Add null guard"],
                        "files_to_modify": ["app.py"],
                        "risk_level": "medium",
                    },
                }
            },
            "execute": {
                "output": {
                    "patch_result": {
                        "modified_files": ["app.py"],
                        "patch_summary": ["Added null guard"],
                        "test_updates": [],
                    }
                }
            },
            "verify": {
                "output": {
                    "verification_result": {
                        "verdict": "PASS",
                        "targeted_tests_passed": True,
                        "smoke_tests_passed": True,
                        "failed_tests": [],
                        "failure_logs": [],
                        "successful_checks": ["python -m unittest"],
                        "ready_for_pr": True,
                    }
                }
            },
        },
        "errors": [],
    }


def create_publishable_repo(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "remote.git"
    worktree = tmp_path / "repo"
    branch_name = "autofix/demo-service/run-001"

    run_git(tmp_path, "init", "--bare", str(remote))
    run_git(tmp_path, "clone", str(remote), str(worktree))
    run_git(worktree, "checkout", "-b", "main")
    run_git(worktree, "config", "user.name", "Tester")
    run_git(worktree, "config", "user.email", "tester@example.com")

    app_file = worktree / "app.py"
    app_file.write_text("def handler(value):\n    return value\n", encoding="utf-8")
    run_git(worktree, "add", "app.py")
    run_git(worktree, "commit", "-m", "Initial commit")
    run_git(worktree, "push", "-u", "origin", "main")
    run_git(worktree, "checkout", "-b", branch_name)

    app_file.write_text("def handler(value):\n    return value or 0\n", encoding="utf-8")
    return worktree, branch_name


def run_git(workdir: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout
