"""Run a full stage-two RepairOrchestrator attempt against the local /tmp demo.

Flow:
1. Start the buggy demo web service and write logs to demo.log
2. Trigger the real HTTP bug so a traceback is emitted
3. Run phase one to produce RepairTask objects from that traceback
4. Adapt the first RepairTask into the flat stage-two task_input
5. Run the real RepairOrchestrator with the configured OpenAI-compatible adapter
6. Re-run the demo test file and print whether the bug was actually fixed
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]

for path in (str(PROJECT_ROOT), str(PACKAGE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv
import requests

from schemas.agent_messages import AgentTurn
from schemas.tool_result import AgentToolResult
from tools.agent_tool import AgentTool
from web_service_guard.runtime.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from web_service_guard.runtime.orchestrator import RepairOrchestrator
from web_service_guard.tools.BashTool import BashTool
from web_service_guard.tools.EditCodeTool import EditCodeTool
from web_service_guard.tools.FileReadTool import FileReadTool
from web_service_guard.tools.GlobTool import GlobTool
from web_service_guard.tools.GrepTool import GrepTool
from web_service_guard.tools.base import BaseTool, ToolRegistry
from web_service_guard.agents.sentinel_agent import SentinelAgent
from web_service_guard.monitoring.traceback_collector import TracebackCollector
from web_service_guard.workflow.repair_pipeline import StageOnePipeline


DEMO_ROOT = Path("/tmp/web_service_guard_verify_demo")
LOG_PATH = DEMO_ROOT / "demo.log"
RUN_LOG_DIR = Path("/tmp/web_service_guard_verify_demo_logs")
TEXT_LOG_PATH = RUN_LOG_DIR / "stage_two_full.log"
JSONL_LOG_PATH = RUN_LOG_DIR / "stage_two_events.jsonl"
HOST = "127.0.0.1"
PORT = 8000
TRIGGER_URL = f"http://{HOST}:{PORT}/total?subtotal=100"
DOTENV_PATH = PACKAGE_ROOT / ".env"


def main() -> None:
    load_runtime_env()
    ensure_demo_ready()
    reset_run_logs()
    reset_demo_log()
    registry = build_registry()
    sentinel = SentinelAgent(
        traceback_collector=TracebackCollector(log_path=str(LOG_PATH))
    )
    pipeline = StageOnePipeline(sentinel_agent=sentinel)
    adapter = OpenAICompatibleLLMAdapter.from_env()
    _append_text(
        "=== ADAPTER CONFIG ===\n"
        f"base_url={adapter.base_url}\n"
        f"model={adapter.model}\n"
        f"timeout_sec={adapter.timeout_sec}\n"
        f"demo_root={DEMO_ROOT}\n"
        f"demo_log={LOG_PATH}\n"
    )
    _append_event(
        {
            "event": "adapter_config",
            "base_url": adapter.base_url,
            "model": adapter.model,
            "timeout_sec": adapter.timeout_sec,
            "demo_root": str(DEMO_ROOT),
            "demo_log": str(LOG_PATH),
        }
    )
    retrying_adapter = RetryingLLMAdapter(adapter)
    logging_main_adapter = LoggingLLMAdapter(retrying_adapter, role="main")
    logging_subagent_adapter = LoggingLLMAdapter(retrying_adapter, role="subagent")
    real_agent_tool = AgentTool(
        llm_adapter=logging_subagent_adapter,
        tool_registry=registry,
        default_max_turns=8,
    )
    logging_agent_tool = LoggingAgentTool(real_agent_tool)
    orchestrator = RepairOrchestrator(
        llm_adapter=logging_main_adapter,
        agent_tool=logging_agent_tool,
        tool_registry=registry,
        default_max_iterations=2,
        default_agent_max_turns=8,
    )

    server = start_demo_server()
    try:
        wait_for_service()
        trigger_bug_request()
        wait_for_traceback()

        repair_tasks = pipeline.run_tasks(
            service="demo-web-service",
            repo=str(DEMO_ROOT),
            branch="main",
            repo_root=str(DEMO_ROOT),
            source="log",
            metadata={"demo_root": str(DEMO_ROOT), "trigger_url": TRIGGER_URL},
        )
        if not repair_tasks:
            raise RuntimeError("Phase one did not produce any RepairTask objects from the demo log.")

        repair_task = repair_tasks[0]
        stage_two_input = {
            "run_id": repair_task.run_id,
            "bug_event": repair_task.bug_event.to_dict(),
            "traceback": repair_task.bug_event.traceback,
            "repo_root": repair_task.repo_root,
            "branch": repair_task.bug_event.branch,
            "max_iterations": repair_task.max_iterations,
        }

        print("=== STAGE TWO INPUT ===")
        print(json.dumps(stage_two_input, ensure_ascii=False, indent=2))
        _append_text("=== STAGE TWO INPUT ===\n" + json.dumps(stage_two_input, ensure_ascii=False, indent=2) + "\n")
        _append_event({"event": "stage_two_input", "payload": stage_two_input})

        result = orchestrator.run(stage_two_input)
        print("\n=== ORCHESTRATOR RESULT ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        _append_text("\n=== ORCHESTRATOR RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        _append_event({"event": "orchestrator_result", "result": result})

        test_returncode, test_output = rerun_demo_tests()
        print("\n=== POST-RUN TEST STATUS ===")
        print(f"returncode: {test_returncode}")
        print(test_output)
        _append_text(
            "\n=== POST-RUN TEST STATUS ===\n"
            f"returncode: {test_returncode}\n{test_output}\n"
        )
        _append_event(
            {
                "event": "post_run_test_status",
                "returncode": test_returncode,
                "output": test_output,
            }
        )

        print("\n=== WORKTREE DIFF ===")
        diff = subprocess.run(
            ["git", "-C", str(DEMO_ROOT), "diff", "--", "app.py", "test_app.py"],
            text=True,
            capture_output=True,
            check=False,
        )
        diff_text = diff.stdout.strip() or "(no diff)"
        print(diff_text)
        _append_text("\n=== WORKTREE DIFF ===\n" + diff_text + "\n")
        _append_event({"event": "worktree_diff", "diff": diff_text})
        print("\n=== RUN LOG FILES ===")
        print(TEXT_LOG_PATH)
        print(JSONL_LOG_PATH)
    finally:
        stop_demo_server(server)


def ensure_demo_ready() -> None:
    if not DEMO_ROOT.exists():
        raise RuntimeError(f"Demo root does not exist: {DEMO_ROOT}")
    for required in ("app.py", "test_app.py", ".git"):
        if not (DEMO_ROOT / required).exists():
            raise RuntimeError(f"Required demo artifact missing: {DEMO_ROOT / required}")


class RetryingLLMAdapter:
    """Small wrapper that retries OpenAI-compatible calls on rate limiting."""

    def __init__(self, inner: OpenAICompatibleLLMAdapter, *, max_retries: int = 3) -> None:
        self._inner = inner
        self._max_retries = max_retries

    def complete(self, **kwargs: Any):
        delay_sec = 5
        for attempt in range(1, self._max_retries + 2):
            try:
                return self._inner.complete(**kwargs)
            except requests.HTTPError as exc:
                status_code = getattr(exc.response, "status_code", None)
                if status_code != 429 or attempt > self._max_retries:
                    raise
                print(
                    f"LLM rate-limited (429). Retrying in {delay_sec}s "
                    f"(attempt {attempt}/{self._max_retries + 1})..."
                )
                time.sleep(delay_sec)
                delay_sec *= 2


class LoggingLLMAdapter:
    """Wrap an adapter and persist each completion turn."""

    def __init__(self, inner: RetryingLLMAdapter, *, role: str) -> None:
        self._inner = inner
        self._role = role
        self._call_index = 0

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[BaseTool],
        system_prompt: str,
        tool_use_context: Any | None = None,
    ) -> AgentTurn:
        self._call_index += 1
        _append_event(
            {
                "event": "llm_request",
                "role": self._role,
                "call_index": self._call_index,
                "system_prompt": system_prompt,
                "tools": [tool.name for tool in tools],
                "message_count": len(messages),
                "messages": messages,
            }
        )
        _append_text(
            f"\n===== LLM REQUEST [{self._role} #{self._call_index}] =====\n"
            f"tools={ [tool.name for tool in tools] }\n"
            f"message_count={len(messages)}\n"
            f"last_message={_shorten(messages[-1] if messages else '')}\n"
        )
        turn = self._inner.complete(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            tool_use_context=tool_use_context,
        )
        _append_event(
            {
                "event": "llm_response",
                "role": self._role,
                "call_index": self._call_index,
                "turn": {
                    "kind": turn.kind,
                    "content": turn.content,
                    "tool_call": asdict(turn.tool_call) if turn.tool_call else None,
                    "raw": turn.raw,
                },
            }
        )
        _append_text(
            f"----- LLM RESPONSE [{self._role} #{self._call_index}] -----\n"
            f"kind={turn.kind}\n"
            f"content={_shorten(turn.content)}\n"
            f"tool_call={_shorten(asdict(turn.tool_call) if turn.tool_call else None)}\n"
        )
        return turn


class LoggingAgentTool(BaseTool):
    """Wrap the real AgentTool and log each invoke payload/result."""

    name = "agent"
    description = "Logging wrapper for the real agent tool"
    input_schema = {}

    def __init__(self, inner: AgentTool) -> None:
        self._inner = inner
        self.name = inner.name
        self.description = inner.description
        self.input_schema = inner.input_schema
        self._call_index = 0

    def invoke(self, payload: dict[str, Any]) -> AgentToolResult:
        self._call_index += 1
        _append_event(
            {
                "event": "agent_invoke",
                "call_index": self._call_index,
                "payload": payload,
            }
        )
        _append_text(
            f"\n===== AGENT INVOKE #{self._call_index} =====\n"
            f"{json.dumps(_json_safe(payload), ensure_ascii=False, indent=2)}\n"
        )
        result = self._inner.invoke(payload)
        _append_event(
            {
                "event": "agent_result",
                "call_index": self._call_index,
                "result": {
                    "agent_type": result.agent_type,
                    "summary": result.summary,
                    "status": result.status,
                    "stop_reason": result.stop_reason,
                    "output": result.output,
                    "errors": result.errors,
                    "used_tools": result.used_tools,
                    "tool_results": [
                        {
                            "name": record.name,
                            "arguments": record.arguments,
                            "status": record.status,
                            "output": record.output,
                            "structured_output": record.structured_output,
                            "summary": record.summary,
                            "error": record.error,
                        }
                        for record in result.tool_results
                    ],
                },
            }
        )
        _append_text(
            f"----- AGENT RESULT #{self._call_index} -----\n"
            f"agent_type={result.agent_type}\n"
            f"status={result.status}\n"
            f"stop_reason={result.stop_reason}\n"
            f"summary={_shorten(result.summary)}\n"
            f"tool_results={_shorten([{'name': r.name, 'status': r.status, 'summary': r.summary, 'error': r.error} for r in result.tool_results], 3000)}\n"
        )
        return result


def _ensure_run_log_dir() -> None:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)


def reset_run_logs() -> None:
    _ensure_run_log_dir()
    TEXT_LOG_PATH.write_text("", encoding="utf-8")
    JSONL_LOG_PATH.write_text("", encoding="utf-8")


def _append_text(text: str) -> None:
    with TEXT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def _append_event(event: dict[str, Any]) -> None:
    with JSONL_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_safe(event), ensure_ascii=False) + "\n")


def _shorten(value: Any, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]..."


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _json_safe(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def load_runtime_env() -> None:
    if DOTENV_PATH.exists():
        load_dotenv(DOTENV_PATH, override=False)
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        os.environ["CCH_API_KEY"] = openai_api_key


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(EditCodeTool())
    registry.register(BashTool())
    return registry


def reset_demo_log() -> None:
    LOG_PATH.write_text("", encoding="utf-8")


def start_demo_server() -> subprocess.Popen[str]:
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(DEMO_ROOT / "app.py")],
        cwd=str(DEMO_ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_demo_server(server: subprocess.Popen[str]) -> None:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def wait_for_service(timeout_sec: int = 10) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with request.urlopen(f"http://{HOST}:{PORT}/missing", timeout=1) as response:
                response.read()
        except error.HTTPError as exc:
            if exc.code == 404:
                return
        except Exception:
            time.sleep(0.2)
            continue
    raise RuntimeError("Demo service did not become reachable in time.")


def trigger_bug_request() -> None:
    try:
        request.urlopen(TRIGGER_URL, timeout=2).read()
    except Exception:
        # The request is expected to fail at the server layer; the important
        # signal is the traceback written into the log.
        pass


def wait_for_traceback(timeout_sec: int = 10) -> None:
    deadline = time.time() + timeout_sec
    marker = "Traceback (most recent call last):"
    while time.time() < deadline:
        text = LOG_PATH.read_text(encoding="utf-8")
        if marker in text and "ValueError" in text:
            return
        time.sleep(0.2)
    raise RuntimeError("Timed out waiting for the demo traceback to appear in the log.")


def rerun_demo_tests() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, str(DEMO_ROOT / "test_app.py")],
        cwd=str(DEMO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    return completed.returncode, output


if __name__ == "__main__":
    main()
