"""Run the real stage-three delivery flow from a mock phase-two result.

This script is for delivery-only demos:
- It uses the real third-stage services (LLM personalization, git publish,
  GitHub PR creation, Feishu notification).
- It does not invoke stage one or stage two.
- It builds a realistic mock phase-two output so the current delivery
  presentation can be previewed or exercised end to end.

Important:
- The target repository must already be on a publishable repair branch.
- The target repository must have uncommitted changes available for commit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

for path in (str(PROJECT_ROOT), str(PACKAGE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from web_service_guard.delivery.service import DeliveryService
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repo_workspace import RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


DEFAULT_REPO_ROOT = Path(r"E:\projeccts\demo-web-service-repo")
DEFAULT_OUTPUT_DIR = Path(".tmp") / "real_stage_three_delivery_demo"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ensure_repo_ready(repo_root)
    current_branch = git_capture(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    remote_url = git_capture(repo_root, "remote", "get-url", "origin").strip()
    status_output = git_capture(repo_root, "status", "--short")

    if current_branch == args.base_branch:
        raise RuntimeError(
            f"Current branch is `{current_branch}`. Switch to a publishable repair branch before running this demo."
        )
    if not status_output.strip():
        raise RuntimeError(
            "The target repository has no uncommitted changes. "
            "Stage three needs a dirty worktree to create a real commit and PR."
        )

    prepared_task = make_prepared_task(
        repo_root=repo_root,
        remote_url=remote_url,
        service_name=args.service_name,
        base_branch=args.base_branch,
        repair_branch=current_branch,
        run_id=args.run_id,
    )
    repair_result = make_mock_phase_two_result(
        run_id=args.run_id,
        service_name=args.service_name,
        root_cause=args.root_cause,
        files_to_modify=args.files_to_modify,
        modified_files=args.modified_files,
        verification_checks=args.successful_checks,
    )

    write_json(output_dir / "prepared_task_mock.json", prepared_task.to_dict())
    write_json(output_dir / "phase_two_mock_result.json", repair_result)

    result = DeliveryService().run(
        prepared_task=prepared_task,
        repair_result=repair_result,
        notification_enabled=not args.skip_notification,
    )
    write_json(output_dir / "delivery_result.json", result)

    print("=== REAL STAGE THREE DELIVERY DEMO ===")
    print(f"repo_root: {repo_root}")
    print(f"remote_url: {remote_url}")
    print(f"base_branch: {args.base_branch}")
    print(f"repair_branch: {current_branch}")
    print(f"run_id: {args.run_id}")
    print(f"delivery_result_json: {output_dir / 'delivery_result.json'}")
    print(f"status: {result.get('status')}")
    print(f"gate_passed: {result.get('gate_passed')}")
    print(f"summary: {result.get('summary')}")
    print(f"pr_url: {((result.get('pr') or {}).get('url'))}")
    notification = result.get("notification") or {}
    print(f"notification_sent: {notification.get('sent')}")
    artifacts = result.get("artifacts") or {}
    personalization = artifacts.get("notification_personalization") or {}
    personalization_result = personalization.get("personalization_result") or {}
    print(f"llm_used: {personalization_result.get('llm_used')}")
    print(f"personalization_success: {personalization_result.get('success')}")
    if personalization_result.get("fallback_reason"):
        print(f"fallback_reason: {personalization_result.get('fallback_reason')}")
    if personalization_result.get("error"):
        print(f"personalization_error: {personalization_result.get('error')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the real stage-three delivery flow from a mock phase-two result.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help="Target local repository workspace that already contains uncommitted changes on a repair branch.",
    )
    parser.add_argument(
        "--service-name",
        default="demo-web-service",
        help="Service name recorded in the mock prepared task and used for profile matching.",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch used for the PR.",
    )
    parser.add_argument(
        "--run-id",
        default="delivery-demo-run-001",
        help="Run ID recorded in the mock phase-two output.",
    )
    parser.add_argument(
        "--root-cause",
        default=(
            "The divide helper did not validate a zero denominator, and the request handler "
            "passed user input through without a safe guard."
        ),
        help="Root-cause text injected into the mock phase-two output.",
    )
    parser.add_argument(
        "--files-to-modify",
        nargs="*",
        default=["demo_service/calculator.py", "demo_service/app.py"],
        help="Files listed in the mock repair plan.",
    )
    parser.add_argument(
        "--modified-files",
        nargs="*",
        default=["demo_service/calculator.py", "demo_service/app.py"],
        help="Files listed in the mock execute result.",
    )
    parser.add_argument(
        "--successful-checks",
        nargs="*",
        default=[
            "GET /divide?a=20&b=5 -> 200",
            "GET /divide?a=10&b=0 -> 400",
            "python -m unittest tests/test_divide.py",
        ],
        help="Verification checks listed in the mock phase-two output.",
    )
    parser.add_argument(
        "--skip-notification",
        action="store_true",
        help="Skip the Feishu notification while still running LLM personalization and PR creation.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the mock input and delivery result will be written.",
    )
    return parser.parse_args()


def ensure_repo_ready(repo_root: Path) -> None:
    if not repo_root.exists():
        raise RuntimeError(f"Repository root does not exist: {repo_root}")
    if not repo_root.is_dir():
        raise RuntimeError(f"Repository root is not a directory: {repo_root}")
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        raise RuntimeError(f"Repository root is not a git repository: {repo_root}")


def make_prepared_task(
    *,
    repo_root: Path,
    remote_url: str,
    service_name: str,
    base_branch: str,
    repair_branch: str,
    run_id: str,
) -> PreparedRepairTask:
    detected_at = _utc_now()
    bug_event = BugEvent(
        event_id=f"evt-{run_id}",
        source="delivery-demo",
        service=service_name,
        repo=remote_url,
        branch=base_branch,
        detected_at=detected_at,
        error_type="ZeroDivisionError",
        error_message="float division by zero",
        error_summary="ZeroDivisionError: float division by zero",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "demo_service/app.py", line 29, in divide\n'
            "    result = divide_numbers(a, b)\n"
            '  File "demo_service/calculator.py", line 7, in divide_numbers\n'
            "    return a / b\n"
            "ZeroDivisionError: float division by zero"
        ),
        fingerprint="deliverydemo1234",
        primary_file=str(repo_root / "demo_service" / "calculator.py"),
        primary_line=7,
    )
    repair_task = RepairTask(
        run_id=run_id,
        bug_event=bug_event,
        repo_root=str(repo_root),
        max_iterations=3,
        created_at=detected_at,
        metadata={"delivery_demo": True},
    )
    workspace = RepoWorkspaceResult(
        repo_url=remote_url,
        repo_root=str(repo_root),
        branch=base_branch,
        workspace_ready=True,
        current_branch=repair_branch,
        repair_branch=repair_branch,
        head_commit=git_capture(repo_root, "rev-parse", "HEAD").strip() or None,
        clean_worktree=False,
        synced_with_remote=True,
    )
    return PreparedRepairTask(repair_task=repair_task, workspace=workspace)


def make_mock_phase_two_result(
    *,
    run_id: str,
    service_name: str,
    root_cause: str,
    files_to_modify: list[str],
    modified_files: list[str],
    verification_checks: list[str],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "final_status": "READY_FOR_PR",
        "current_stage": "READY_FOR_PR",
        "iterations_used": 1,
        "summary": "VERDICT: PASS",
        "artifacts": {
            "plan": {
                "summary": f"{service_name} repair plan",
                "output": {
                    "root_cause_analysis": {
                        "root_cause": root_cause,
                        "evidence": [
                            "Traceback points to divide_numbers in calculator.py",
                            "The /divide route passed the denominator through without a guard",
                        ],
                        "risk_level": "medium",
                    },
                    "repair_plan": {
                        "root_cause": root_cause,
                        "fix_plan": [
                            "Add denominator validation in the helper",
                            "Return a friendlier client error from the route",
                        ],
                        "files_to_modify": list(files_to_modify),
                        "risk_level": "medium",
                    },
                },
            },
            "execute": {
                "summary": "Applied the repair patch",
                "output": {
                    "patch_result": {
                        "modified_files": list(modified_files),
                        "patch_summary": [
                            "Added validation for divide-by-zero input",
                            "Adjusted endpoint error handling for invalid divide requests",
                        ],
                        "test_updates": [],
                    }
                },
            },
            "verify": {
                "summary": "VERDICT: PASS",
                "output": {
                    "verification_result": {
                        "verdict": "PASS",
                        "targeted_tests_passed": True,
                        "smoke_tests_passed": True,
                        "failed_tests": [],
                        "failure_logs": [],
                        "successful_checks": list(verification_checks),
                        "ready_for_pr": True,
                    }
                },
            },
        },
        "errors": [],
    }


def git_capture(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
