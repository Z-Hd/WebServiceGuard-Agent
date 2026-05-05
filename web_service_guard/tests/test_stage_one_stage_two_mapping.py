"""Tests for the phase-one to phase-two task-input adapter."""

from __future__ import annotations

from web_service_guard.agents.sentinel_agent import _utc_now
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repo_workspace import RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


def test_prepared_repair_task_maps_to_stage_two_input() -> None:
    bug_event = BugEvent(
        event_id="evt-001",
        source="log",
        service="demo-service",
        repo="owner/demo-service",
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
        repo_root="E:/repos/demo-service",
        max_iterations=2,
        created_at=_utc_now(),
    )
    prepared_task = PreparedRepairTask(
        repair_task=repair_task,
        workspace=RepoWorkspaceResult(
            repo_url="owner/demo-service",
            repo_root="E:/workspaces/demo-service",
            branch="main",
            workspace_ready=True,
            current_branch="autofix/demo/current",
            repair_branch="autofix/demo/repair",
            head_commit="abc",
            clean_worktree=True,
            synced_with_remote=True,
        ),
    )

    task_input = prepared_task.to_stage_two_input()

    assert task_input["run_id"] == "run-001"
    assert task_input["bug_event"]["event_id"] == "evt-001"
    assert task_input["traceback"] == "Traceback (most recent call last): ..."
    assert task_input["repo_root"] == "E:/workspaces/demo-service"
    assert task_input["branch"] == "autofix/demo/repair"
    assert task_input["max_iterations"] == 2


def test_prepared_repair_task_mapping_falls_back_to_current_branch_then_bug_event_branch() -> None:
    bug_event = BugEvent(
        event_id="evt-002",
        source="log",
        service="demo-service",
        repo="owner/demo-service",
        branch="main",
        detected_at=_utc_now(),
        error_type="ValueError",
        error_message="bad value",
        error_summary="ValueError: bad value",
        traceback="Traceback (most recent call last): ...",
        fingerprint="abc12346",
    )
    repair_task = RepairTask(
        run_id="run-002",
        bug_event=bug_event,
        repo_root="E:/repos/demo-service",
        max_iterations=3,
        created_at=_utc_now(),
    )

    prepared_with_current_only = PreparedRepairTask(
        repair_task=repair_task,
        workspace=RepoWorkspaceResult(
            repo_url="owner/demo-service",
            repo_root="E:/workspaces/demo-service",
            branch="main",
            workspace_ready=True,
            current_branch="autofix/demo/current-only",
            repair_branch=None,
            head_commit="abc",
            clean_worktree=True,
            synced_with_remote=True,
        ),
    )
    assert prepared_with_current_only.to_stage_two_input()["branch"] == "autofix/demo/current-only"

    prepared_with_no_workspace_branch = PreparedRepairTask(
        repair_task=repair_task,
        workspace=RepoWorkspaceResult(
            repo_url="owner/demo-service",
            repo_root="E:/workspaces/demo-service",
            branch="main",
            workspace_ready=True,
            current_branch=None,
            repair_branch=None,
            head_commit="abc",
            clean_worktree=True,
            synced_with_remote=True,
        ),
    )
    assert prepared_with_no_workspace_branch.to_stage_two_input()["branch"] == "main"
