"""One-command reset + run + summarize flow for the /tmp stage-two demo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = Path("/tmp/web_service_guard_verify_demo")
RUN_SCRIPT = PACKAGE_ROOT / "scripts" / "tmp_demo_stage_two_run.py"
RUN_LOG_DIR = Path("/tmp/web_service_guard_verify_demo_logs")
TEXT_LOG_PATH = RUN_LOG_DIR / "stage_two_full.log"
JSONL_LOG_PATH = RUN_LOG_DIR / "stage_two_events.jsonl"


def main() -> None:
    ensure_demo_ready()

    print("=== RESET DEMO ===")
    reset_demo_repo()
    remove_runtime_artifacts()
    print_git_status("after reset")

    print("\n=== PRE-RUN TEST STATUS ===")
    pre_returncode, pre_output = run_demo_tests()
    print(f"returncode: {pre_returncode}")
    print(pre_output)

    if pre_returncode == 0:
        raise RuntimeError(
            "The demo is expected to fail before repair, but tests already passed. "
            "Refusing to continue because the buggy baseline is missing."
        )

    print("\n=== RUN STAGE TWO DEMO ===")
    run_stage_two_demo()

    print("\n=== POST-RUN TEST STATUS ===")
    post_returncode, post_output = run_demo_tests()
    print(f"returncode: {post_returncode}")
    print(post_output)

    print("\n=== FINAL GIT STATUS ===")
    print_git_status("after stage-two run")

    print("\n=== FINAL DIFF ===")
    show_diff()

    print("\n=== LOG FILES ===")
    print(TEXT_LOG_PATH)
    print(JSONL_LOG_PATH)

    print("\n=== SUMMARY ===")
    summary = {
        "pre_run_test_returncode": pre_returncode,
        "post_run_test_returncode": post_returncode,
        "ready_for_pr_detected": detect_ready_for_pr(),
        "text_log_path": str(TEXT_LOG_PATH),
        "jsonl_log_path": str(JSONL_LOG_PATH),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def ensure_demo_ready() -> None:
    if not DEMO_ROOT.exists():
        raise RuntimeError(f"Demo root does not exist: {DEMO_ROOT}")
    for required in ("app.py", "test_app.py", ".git"):
        if not (DEMO_ROOT / required).exists():
            raise RuntimeError(f"Required demo artifact missing: {DEMO_ROOT / required}")
    if not RUN_SCRIPT.exists():
        raise RuntimeError(f"Stage-two run script not found: {RUN_SCRIPT}")


def reset_demo_repo() -> None:
    run_checked(["git", "-C", str(DEMO_ROOT), "restore", "app.py", "test_app.py", "README.md"])
    run_checked(["git", "-C", str(DEMO_ROOT), "clean", "-fd"])


def remove_runtime_artifacts() -> None:
    for path in (DEMO_ROOT / "demo.log",):
        if path.exists():
            path.unlink()


def run_demo_tests() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, str(DEMO_ROOT / "test_app.py")],
        cwd=str(DEMO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    return completed.returncode, output


def run_stage_two_demo() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    completed = subprocess.run(
        [sys.executable, str(RUN_SCRIPT)],
        cwd=str(PACKAGE_ROOT),
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Stage-two demo script exited with {completed.returncode}. "
            f"Check {TEXT_LOG_PATH} and {JSONL_LOG_PATH} for details."
        )


def print_git_status(label: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(DEMO_ROOT), "status", "--short"],
        text=True,
        capture_output=True,
        check=False,
    )
    print(f"[{label}]")
    print(completed.stdout.strip() or "(clean)")


def show_diff() -> None:
    completed = subprocess.run(
        ["git", "-C", str(DEMO_ROOT), "diff", "--", "app.py", "test_app.py"],
        text=True,
        capture_output=True,
        check=False,
    )
    print(completed.stdout.strip() or "(no diff)")


def detect_ready_for_pr() -> bool:
    if not JSONL_LOG_PATH.exists():
        return False
    try:
        lines = JSONL_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("event") != "orchestrator_result":
            continue
        result = payload.get("result") or {}
        return result.get("final_status") == "READY_FOR_PR"
    return False


def run_checked(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )


if __name__ == "__main__":
    main()
