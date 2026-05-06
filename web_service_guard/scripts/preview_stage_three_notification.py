"""Preview the current stage-three personalized notification from a mock phase-two result.

This script does not push git branches, create a real PR, or send a webhook.
It builds a realistic mock phase-two output and then runs the real third-stage
notification-personalization path so we can inspect the generated message.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

for path in (str(PROJECT_ROOT), str(PACKAGE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from web_service_guard.delivery.developer_profile_service import DeveloperProfileService
from web_service_guard.delivery.notification_personalizer import NotificationPersonalizer
from web_service_guard.delivery.notify_service import NotifyService
from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.prepared_repair_task import PreparedRepairTask
from web_service_guard.schemas.repo_workspace import RepoWorkspaceResult
from web_service_guard.schemas.repair_task import RepairTask


DEFAULT_OUTPUT_DIR = Path(".tmp") / "stage_three_notification_preview"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prepared_task = make_prepared_task(
        service_name=args.service_name,
        repo_root=args.repo_root.resolve(),
    )
    repair_result = make_mock_phase_two_result(run_id=args.run_id)
    pr_result = {
        "created": True,
        "url": args.pr_url,
        "number": 1,
        "title": "Auto-fix: demo-service - ZeroDivisionError",
        "body": "(preview)",
        "repo_full_name": "acme/demo-service",
        "head": "autofix/demo-service/run-001",
        "base": "main",
    }

    profile_service = DeveloperProfileService()
    personalizer = NotificationPersonalizer()
    notify_service = NotifyService()

    profile_resolution = profile_service.resolve_profile(
        prepared_task=prepared_task,
        repair_result=repair_result,
    )
    personalization = personalizer.personalize(
        prepared_task=prepared_task,
        repair_result=repair_result,
        pr_result=pr_result,
        profile_resolution=profile_resolution,
    )
    payload = notify_service.build_payload(
        prepared_task=prepared_task,
        repair_result=repair_result,
        pr_result=pr_result,
        notification_text=personalization.text if personalization.success else None,
    )

    prepared_task_path = output_dir / "prepared_task_mock.json"
    repair_result_path = output_dir / "phase_two_mock_result.json"
    preview_json_path = output_dir / "notification_preview.json"
    preview_md_path = output_dir / "notification_preview.md"

    write_json(prepared_task_path, prepared_task.to_dict())
    write_json(repair_result_path, repair_result)
    write_json(
        preview_json_path,
        {
            "profile_resolution": profile_resolution.to_dict(),
            "personalization_result": personalization.to_dict(),
            "payload": payload,
        },
    )
    markdown = extract_markdown_from_payload(payload)
    preview_md_path.write_text(markdown, encoding="utf-8")

    print("=== STAGE THREE NOTIFICATION PREVIEW ===")
    print(f"service_name: {args.service_name}")
    print(f"profile_matched_by: {profile_resolution.matched_by}")
    print(f"profile_source: {profile_resolution.source_path}")
    print(f"llm_used: {personalization.llm_used}")
    print(f"personalization_success: {personalization.success}")
    if personalization.fallback_reason:
        print(f"fallback_reason: {personalization.fallback_reason}")
    if personalization.error:
        print(f"personalization_error: {personalization.error}")
    print(f"prepared_task_mock: {prepared_task_path}")
    print(f"phase_two_mock_result: {repair_result_path}")
    print(f"notification_preview_json: {preview_json_path}")
    print(f"notification_preview_md: {preview_md_path}")
    print("\n=== FINAL MARKDOWN ===")
    print(markdown)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the third-stage personalized notification.")
    parser.add_argument(
        "--service-name",
        default="demo-service",
        help="Bug-event service name used to select the developer profile.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root recorded in the mock prepared task.",
    )
    parser.add_argument(
        "--run-id",
        default="run-preview-001",
        help="Run ID recorded in the mock phase-two output.",
    )
    parser.add_argument(
        "--pr-url",
        default="https://github.com/acme/demo-service/pull/123",
        help="PR URL injected into the preview payload.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where preview artifacts will be written.",
    )
    return parser.parse_args()


def make_prepared_task(*, service_name: str, repo_root: Path) -> PreparedRepairTask:
    detected_at = _utc_now()
    bug_event = BugEvent(
        event_id="evt-preview-001",
        source="preview",
        service=service_name,
        repo="acme/demo-service",
        branch="main",
        detected_at=detected_at,
        error_type="ZeroDivisionError",
        error_message="float division by zero",
        error_summary="ZeroDivisionError: float division by zero",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "app.py", line 29, in divide\n'
            "    result = divide_numbers(a, b)\n"
            '  File "calculator.py", line 7, in divide_numbers\n'
            "    return a / b\n"
            "ZeroDivisionError: float division by zero"
        ),
        fingerprint="preview1234",
        primary_file="demo_service/calculator.py",
        primary_line=7,
    )
    repair_task = RepairTask(
        run_id="run-preview-001",
        bug_event=bug_event,
        repo_root=str(repo_root),
        max_iterations=3,
        created_at=detected_at,
        metadata={"preview": True},
    )
    workspace = RepoWorkspaceResult(
        repo_url=bug_event.repo,
        repo_root=str(repo_root),
        branch="main",
        workspace_ready=True,
        current_branch="autofix/demo-service/run-preview-001",
        repair_branch="autofix/demo-service/run-preview-001",
        head_commit="HEAD",
        clean_worktree=True,
        synced_with_remote=True,
    )
    return PreparedRepairTask(repair_task=repair_task, workspace=workspace)


def make_mock_phase_two_result(*, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "final_status": "READY_FOR_PR",
        "current_stage": "READY_FOR_PR",
        "iterations_used": 1,
        "summary": "VERDICT: PASS",
        "artifacts": {
            "plan": {
                "summary": "ZeroDivisionError repair plan",
                "output": {
                    "root_cause_analysis": {
                        "root_cause": (
                            "The divide helper did not validate a zero denominator, and the /divide "
                            "endpoint passed user input through without a safe guard."
                        ),
                        "evidence": [
                            "calculator.py returns a / b without checking b == 0",
                            "app.py calls divide_numbers(a, b) directly from the /divide handler",
                        ],
                        "risk_level": "medium",
                    },
                    "repair_plan": {
                        "root_cause": "Missing zero-denominator validation",
                        "fix_plan": [
                            "Add a zero check in divide_numbers",
                            "Return a 400-style bad request response for invalid divide input",
                        ],
                        "files_to_modify": [
                            "demo_service/calculator.py",
                            "demo_service/app.py",
                        ],
                        "risk_level": "medium",
                    },
                },
            },
            "execute": {
                "summary": "Applied the repair patch",
                "output": {
                    "patch_result": {
                        "modified_files": [
                            "demo_service/calculator.py",
                            "demo_service/app.py",
                        ],
                        "patch_summary": [
                            "Added denominator validation in calculator.py",
                            "Adjusted /divide error handling in app.py",
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
                        "successful_checks": [
                            "GET /divide?a=20&b=5 -> 200",
                            "GET /divide?a=10&b=0 -> 400",
                            "python -m unittest tests/test_divide.py",
                        ],
                        "ready_for_pr": True,
                    }
                },
            },
        },
        "errors": [],
    }


def extract_markdown_from_payload(payload: dict[str, Any]) -> str:
    post = (((payload.get("content") or {}).get("post") or {}).get("zh_cn") or {})
    content = post.get("content") or []
    lines: list[str] = []
    for row in content:
        if not isinstance(row, list):
            continue
        for block in row:
            if isinstance(block, dict) and block.get("tag") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.append(text)
    return "\n".join(lines).strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
