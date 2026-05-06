"""Inspect how the local buggy demo flows through monitor -> RepairTask.

This script is intentionally phase-one centric:

1. Read traceback candidates from the demo log
2. Normalize them into BugEvent objects
3. Build RepairTask objects
4. Optionally attempt PreparedRepairTask / stage-two input when the demo repo
   is already a usable git workspace

It is meant for local debugging and explanation, not for full automated repair.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

for path in (str(PROJECT_ROOT), str(PACKAGE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.workflow.stage1_pipeline import StageOnePipeline


DEFAULT_DEMO_ROOT = Path("/tmp/web_service_guard_verify_demo")
DEFAULT_LOG_PATH = DEFAULT_DEMO_ROOT / "demo.log"
DEFAULT_SERVICE = "demo-web-service"
DEFAULT_BRANCH = "main"


def main() -> None:
    args = parse_args()
    demo_root = args.demo_root.resolve()
    log_path = args.log_path.resolve()
    repo_value = str(args.repo) if args.repo else str(demo_root)

    print("=== DEMO MONITOR -> REPAIR TASK ===")
    print(f"demo_root: {demo_root}")
    print(f"log_path: {log_path}")
    print(f"service: {args.service}")
    print(f"repo: {repo_value}")
    print(f"branch: {args.branch}")

    ensure_demo_inputs(demo_root, log_path)

    collector = TracebackCollector(log_path=str(log_path))
    sentinel = SentinelAgent(traceback_collector=collector)
    trigger = sentinel.build_trigger(
        service=args.service,
        repo=repo_value,
        branch=args.branch,
        source="log",
        metadata={"demo_root": str(demo_root), "log_path": str(log_path)},
    )

    candidates = collector.collect_tracebacks(
        service=args.service,
        source="log",
        detected_at=trigger.detected_at,
    )
    bug_events = sentinel.collect_bug_events(trigger)
    repair_tasks = sentinel.create_repair_tasks(trigger, repo_root=str(demo_root))

    print_section("TracebackCandidates", [candidate.to_dict() for candidate in candidates])
    print_section("BugEvents", [event.to_dict() for event in bug_events])
    print_section("RepairTasks", [task.to_dict() for task in repair_tasks])

    if not repair_tasks:
        print("\nNo RepairTask objects were created.")
        print("Make sure the demo service has already written a traceback to the log.")
        print_trigger_instructions(log_path)
        return

    if not args.attempt_prepare:
        print(
            "\nPreparedRepairTask/stage-two input step skipped. "
            "Use --attempt-prepare if the demo directory is already a valid git workspace."
        )
        return

    pipeline = StageOnePipeline(sentinel_agent=sentinel)
    try:
        prepared_tasks = pipeline.run_prepared_tasks(
            service=args.service,
            repo=repo_value,
            branch=args.branch,
            repo_root=str(demo_root),
            source="log",
            metadata={"demo_root": str(demo_root), "log_path": str(log_path)},
        )
    except Exception as exc:
        print("\nPreparedRepairTask step failed:")
        print(str(exc))
        print(
            "This usually means the demo directory is not yet a usable git workspace "
            "for RepoWorkspaceManager."
        )
        return

    print_section("PreparedRepairTasks", [task.to_dict() for task in prepared_tasks])
    print_section("StageTwoInputs", [task.to_stage_two_input() for task in prepared_tasks])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show how the local buggy demo becomes TracebackCandidate, BugEvent, and RepairTask objects."
    )
    parser.add_argument(
        "--demo-root",
        type=Path,
        default=DEFAULT_DEMO_ROOT,
        help="Path to the local buggy demo directory.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to the demo log file containing traceback output.",
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_SERVICE,
        help="Service name passed into phase one.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repo identifier stored in BugEvent. Defaults to the demo root path.",
    )
    parser.add_argument(
        "--branch",
        default=DEFAULT_BRANCH,
        help="Branch value stored in BugEvent/RepairTask.",
    )
    parser.add_argument(
        "--attempt-prepare",
        action="store_true",
        help="Also try the PreparedRepairTask/stage-two input step if the demo directory is a valid git workspace.",
    )
    return parser.parse_args()


def ensure_demo_inputs(demo_root: Path, log_path: Path) -> None:
    if not demo_root.exists():
        raise RuntimeError(f"Demo root does not exist: {demo_root}")
    if not log_path.exists():
        raise RuntimeError(
            f"Log file does not exist: {log_path}\n"
            "Start the demo service and trigger the bug first so a traceback is written."
        )


def print_section(title: str, payload: list[dict[str, Any]]) -> None:
    print(f"\n=== {title} ({len(payload)}) ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_trigger_instructions(log_path: Path) -> None:
    print("\nSuggested local flow:")
    print(f"1. Start the service and redirect logs into {log_path}")
    print(f"   python3 /tmp/web_service_guard_verify_demo/app.py >> {log_path} 2>&1")
    print('2. Trigger the bug:')
    print('   curl "http://127.0.0.1:8000/total?subtotal=100"')
    print("3. Re-run this script.")


if __name__ == "__main__":
    main()
