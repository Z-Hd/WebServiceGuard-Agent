"""Run a one-shot three-stage demo against a live web runtime and separate repair workspace.

This script is intended for demo use:

1. A buggy web service is already running from the runtime directory.
2. The script triggers a real failing request against that service.
3. It captures the newly appended traceback from the runtime log.
4. It runs phase one against that captured traceback while preparing the separate repair workspace.
5. It runs phase two against the prepared workspace.
6. If phase two reaches READY_FOR_PR, it runs the real phase-three delivery flow.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# Some existing stage-two modules still use package-relative imports such as
# `from schemas...` / `from runtime...`, so we expose both roots here.
for path in (str(PROJECT_ROOT), str(PACKAGE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.delivery.service import DeliveryService
from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.runtime.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from web_service_guard.runtime.orchestrator import RepairOrchestrator
from web_service_guard.tools.BashTool import BashTool
from web_service_guard.tools.EditCodeTool import EditCodeTool
from web_service_guard.tools.FileReadTool import FileReadTool
from web_service_guard.tools.GlobTool import GlobTool
from web_service_guard.tools.GrepTool import GrepTool
from web_service_guard.tools.base import ToolRegistry
from web_service_guard.workflow.repair_pipeline import StageOnePipeline


DEFAULT_RUNTIME_ROOT = Path(r"E:\projeccts\demo-web-service-runtime")
DEFAULT_WORKSPACE_ROOT = Path(r"E:\projeccts\demo-web-service-repo")
DEFAULT_TRIGGER_URL = "http://127.0.0.1:5050/divide?a=10&b=0"
DEFAULT_HEALTH_URL = "http://127.0.0.1:5050/health"
DEFAULT_SERVICE_NAME = "demo-web-service"
DEFAULT_BASE_BRANCH = "main"


def main() -> None:
    args = parse_args()
    prefer_openai_api_key_from_env()
    runtime_root = args.runtime_root.resolve()
    workspace_root = args.workspace_root.resolve()
    runtime_log_path = (
        args.runtime_log.resolve()
        if args.runtime_log is not None
        else (runtime_root / "logs" / "demo_service.log").resolve()
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=== ONE-SHOT THREE-STAGE DEMO ===")
    print(f"runtime_root: {runtime_root}")
    print(f"runtime_log_path: {runtime_log_path}")
    print(f"workspace_root: {workspace_root}")
    print(f"trigger_url: {args.trigger_url}")

    ensure_paths(runtime_root, runtime_log_path, workspace_root)
    ensure_required_env()
    ensure_runtime_service_is_reachable(args.health_url)

    remote_repo = infer_remote_repo(workspace_root)
    print(f"workspace remote: {remote_repo}")

    baseline = read_log_bytes(runtime_log_path)
    response = trigger_bug(args.trigger_url)
    appended_text = wait_for_new_traceback(
        runtime_log_path=runtime_log_path,
        baseline=baseline,
        timeout_sec=args.traceback_timeout_sec,
    )
    captured_log_path = output_dir / "captured_runtime_traceback.log"
    captured_log_path.write_text(appended_text, encoding="utf-8")
    print(f"captured runtime traceback written to: {captured_log_path}")

    stage_one = build_stage_one_pipeline(captured_log_path)
    prepared_tasks = stage_one.run_prepared_tasks(
        service=args.service_name,
        repo=remote_repo,
        branch=args.base_branch,
        repo_root=str(workspace_root),
        source="log",
        metadata={
            "runtime_root": str(runtime_root),
            "runtime_log_path": str(runtime_log_path),
            "trigger_url": args.trigger_url,
            "trigger_status_code": response.status_code,
        },
    )
    if not prepared_tasks:
        raise RuntimeError("Phase one did not produce any PreparedRepairTask objects.")

    print(f"phase_one prepared task count: {len(prepared_tasks)}")
    prepared_task = prepared_tasks[0]
    write_json(output_dir / "phase_one_prepared_task.json", prepared_task.to_dict())
    stage_two_input = prepared_task.to_stage_two_input()
    write_json(output_dir / "phase_two_input.json", stage_two_input)

    orchestrator = build_orchestrator()
    repair_result = orchestrator.run(stage_two_input)
    write_json(output_dir / "phase_two_result.json", repair_result)
    print(f"phase_two final_status: {repair_result.get('final_status')}")
    print_phase_two_diagnostics(repair_result)

    delivery_result: dict[str, Any] | None = None
    if repair_result.get("final_status") == "READY_FOR_PR":
        delivery_result = DeliveryService().run(
            prepared_task=prepared_task,
            repair_result=repair_result,
            notification_enabled=not args.skip_notification,
        )
        write_json(output_dir / "phase_three_result.json", delivery_result)
        print(f"phase_three status: {delivery_result.get('status')}")
        print(f"pr_url: {((delivery_result.get('pr') or {}).get('url'))}")
    else:
        print("phase_three skipped because phase_two did not reach READY_FOR_PR")

    write_summary(
        output_dir=output_dir,
        prepared_task=prepared_task.to_dict(),
        stage_two_input=stage_two_input,
        repair_result=repair_result,
        delivery_result=delivery_result,
        trigger_status_code=response.status_code,
        runtime_log_path=runtime_log_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a one-shot three-stage demo against the live web demo runtime.")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=DEFAULT_RUNTIME_ROOT,
        help="Directory where the buggy web service is running.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACE_ROOT,
        help="Separate repair workspace that phase two and three will modify.",
    )
    parser.add_argument(
        "--runtime-log",
        type=Path,
        default=None,
        help="Optional explicit runtime log file path. Defaults to <runtime-root>/logs/demo_service.log.",
    )
    parser.add_argument(
        "--trigger-url",
        default=DEFAULT_TRIGGER_URL,
        help="HTTP endpoint that should trigger the runtime bug.",
    )
    parser.add_argument(
        "--health-url",
        default=DEFAULT_HEALTH_URL,
        help="HTTP health endpoint used to verify the runtime service is already running.",
    )
    parser.add_argument(
        "--service-name",
        default=DEFAULT_SERVICE_NAME,
        help="Service name passed into phase one.",
    )
    parser.add_argument(
        "--base-branch",
        default=DEFAULT_BASE_BRANCH,
        help="Base branch name passed into phase one.",
    )
    parser.add_argument(
        "--traceback-timeout-sec",
        type=int,
        default=15,
        help="How long to wait for the runtime log to append a new traceback after triggering the bug.",
    )
    parser.add_argument(
        "--skip-notification",
        action="store_true",
        help="Skip phase-three Feishu notification while still creating the PR.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".tmp") / "web_demo_one_shot_three_stage",
        help="Directory where intermediate artifacts and results will be written.",
    )
    return parser.parse_args()


def ensure_paths(runtime_root: Path, runtime_log_path: Path, workspace_root: Path) -> None:
    if not runtime_root.exists():
        raise RuntimeError(f"runtime_root does not exist: {runtime_root}")
    if not workspace_root.exists():
        raise RuntimeError(f"workspace_root does not exist: {workspace_root}")
    if not runtime_log_path.exists():
        raise RuntimeError(
            f"runtime_log_path does not exist: {runtime_log_path}\n"
            "Start the web demo at least once so the log file is created."
        )


def ensure_required_env() -> None:
    missing: list[str] = []
    if not (get_env("CCH_API_KEY") or get_env("OPENAI_API_KEY")):
        missing.append("OPENAI_API_KEY or CCH_API_KEY")
    if not get_env("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN")
    if not get_env("FEISHU_WEBHOOK_URL"):
        missing.append("FEISHU_WEBHOOK_URL")
    if missing:
        raise RuntimeError(f"Missing required environment configuration: {', '.join(missing)}")


def get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def prefer_openai_api_key_from_env() -> None:
    """Prefer the .env-provided OPENAI_API_KEY over an inherited CCH_API_KEY.

    The existing second-stage adapter resolves keys in this order:
    CCH_API_KEY -> OPENAI_API_KEY. For this demo we want the current .env
    OpenAI-compatible Ark credentials to win deterministically.
    """

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        os.environ.pop("CCH_API_KEY", None)


def ensure_runtime_service_is_reachable(health_url: str) -> None:
    try:
        response = requests.get(health_url, timeout=5)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach the runtime web service at {health_url}. "
            "Start the demo service first."
        ) from exc
    if response.status_code != 200:
        raise RuntimeError(
            f"Runtime health check failed with status {response.status_code} at {health_url}."
        )


def infer_remote_repo(workspace_root: Path) -> str:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Failed to resolve git remote origin.")
    return completed.stdout.strip()


def read_log_bytes(runtime_log_path: Path) -> bytes:
    return runtime_log_path.read_bytes()


def trigger_bug(trigger_url: str) -> requests.Response:
    print(f"triggering bug via: {trigger_url}")
    response = requests.get(trigger_url, timeout=10)
    print(f"trigger response status: {response.status_code}")
    if response.status_code < 500:
        raise RuntimeError(
            f"Expected the trigger endpoint to fail with a 5xx response, got {response.status_code}."
        )
    return response


def wait_for_new_traceback(
    *,
    runtime_log_path: Path,
    baseline: bytes,
    timeout_sec: int,
) -> str:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current = runtime_log_path.read_bytes()
        if len(current) > len(baseline):
            appended = current[len(baseline):].decode("utf-8", errors="ignore")
            if "Traceback (most recent call last):" in appended:
                return appended
        time.sleep(0.5)
    raise RuntimeError(
        f"Timed out after {timeout_sec} second(s) waiting for a newly appended traceback in {runtime_log_path}."
    )


def build_stage_one_pipeline(runtime_log_path: Path) -> StageOnePipeline:
    sentinel_agent = SentinelAgent(
        traceback_collector=TracebackCollector(log_path=str(runtime_log_path)),
    )
    return StageOnePipeline(sentinel_agent=sentinel_agent)


def build_orchestrator() -> RepairOrchestrator:
    adapter = OpenAICompatibleLLMAdapter.from_env()
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(EditCodeTool())
    registry.register(BashTool())
    return RepairOrchestrator(
        llm_adapter=adapter,
        subagent_llm_adapter=adapter,
        tool_registry=registry,
        default_agent_max_turns=6,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary(
    *,
    output_dir: Path,
    prepared_task: dict[str, Any],
    stage_two_input: dict[str, Any],
    repair_result: dict[str, Any],
    delivery_result: dict[str, Any] | None,
    trigger_status_code: int,
    runtime_log_path: Path,
) -> None:
    summary = {
        "trigger_status_code": trigger_status_code,
        "runtime_log_path": str(runtime_log_path),
        "prepared_task_workspace_ready": ((prepared_task.get("workspace") or {}).get("workspace_ready")),
        "prepared_task_repair_branch": ((prepared_task.get("workspace") or {}).get("repair_branch")),
        "stage_two_input_repo_root": stage_two_input.get("repo_root"),
        "stage_two_final_status": repair_result.get("final_status"),
        "delivery_status": None if delivery_result is None else delivery_result.get("status"),
        "pr_url": None if delivery_result is None else ((delivery_result.get("pr") or {}).get("url")),
    }
    write_json(output_dir / "summary.json", summary)


def print_phase_two_diagnostics(repair_result: dict[str, Any]) -> None:
    print("\n=== PHASE TWO DIAGNOSTICS ===")
    print(f"run_id: {repair_result.get('run_id')}")
    print(f"final_status: {repair_result.get('final_status')}")
    print(f"iterations_used: {repair_result.get('iterations_used')}")

    artifacts = repair_result.get("artifacts") or {}
    for stage_name in ("explore", "plan", "execute", "verify"):
        stage_payload = artifacts.get(stage_name)
        if not isinstance(stage_payload, dict):
            print(f"- {stage_name}: not reached")
            continue

        print(
            f"- {stage_name}: status={stage_payload.get('status')} "
            f"stop_reason={stage_payload.get('stop_reason')}"
        )
        summary = str(stage_payload.get("summary", "")).strip()
        if summary:
            print(f"  summary: {shorten_for_console(summary)}")

        if stage_name == "plan":
            print(
                f"  fallback_used={stage_payload.get('fallback_used')} "
                f"fallback_reason={stage_payload.get('fallback_reason')}"
            )
            fallback_files = stage_payload.get("fallback_files_to_modify") or []
            if fallback_files:
                print(f"  fallback_files_to_modify={fallback_files}")
            output = stage_payload.get("output") or {}
            plan_files = ((output.get("repair_plan") or {}).get("files_to_modify") or [])
            evidence = ((output.get("root_cause_analysis") or {}).get("evidence") or [])
            print(f"  files_to_modify={plan_files}")
            print(f"  evidence_count={len(evidence)}")

        if stage_name == "execute":
            output = stage_payload.get("output") or {}
            modified_files = ((output.get("patch_result") or {}).get("modified_files") or [])
            print(f"  modified_files={modified_files}")
            print(f"  need_replan={output.get('need_replan')}")

        if stage_name == "verify":
            output = stage_payload.get("output") or {}
            verification = output.get("verification_result") or {}
            print(
                f"  verdict={verification.get('verdict')} "
                f"ready_for_pr={verification.get('ready_for_pr')}"
            )
            failed_tests = verification.get("failed_tests") or []
            if failed_tests:
                print(f"  failed_tests={failed_tests}")
            environment_limitations = verification.get("environment_limitations") or []
            if environment_limitations:
                print(f"  environment_limitations={environment_limitations}")
            bash_checks = verification.get("bash_checks") or []
            for idx, check in enumerate(bash_checks, start=1):
                print(
                    f"  bash_check[{idx}]: status={check.get('status')} "
                    f"command={check.get('command')} "
                    f"exit_code={check.get('exit_code')} "
                    f"env_failure={check.get('is_environment_failure')}"
                )

        errors = stage_payload.get("errors") or []
        if errors:
            print("  errors:")
            for error in errors:
                print(
                    f"    - code={error.get('code')} "
                    f"source={error.get('source')} "
                    f"message={shorten_for_console(str(error.get('message', '')))}"
                )

    top_level_errors = repair_result.get("errors") or []
    if top_level_errors:
        print("top_level_errors:")
        for error in top_level_errors:
            print(
                f"  - code={error.get('code')} "
                f"source={error.get('source')} "
                f"message={shorten_for_console(str(error.get('message', '')))}"
            )


def shorten_for_console(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + " ..."


if __name__ == "__main__":
    main()
