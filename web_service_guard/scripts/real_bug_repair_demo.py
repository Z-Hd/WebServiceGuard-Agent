"""Run a real orchestrator repair attempt against a tiny buggy web app fixture."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.openai_compatible_adapter import OpenAICompatibleLLMAdapter
from runtime.orchestrator import run
from schemas.agent_messages import AgentTurn
from schemas.tool_result import AgentToolResult
from tools.agent_tool import AgentTool
from tools.BashTool import BashTool
from tools.EditCodeTool import EditCodeTool
from tools.FileReadTool import FileReadTool
from tools.GlobTool import GlobTool
from tools.GrepTool import GrepTool
from tools.base import BaseTool, ToolRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "repos"
WRITABLE_FIXTURE_DIR = Path("/tmp/web_service_guard_demo")
FIXTURE_DIR = WRITABLE_FIXTURE_DIR
TEST_FILE = WRITABLE_FIXTURE_DIR / "test_demo_webapp.py"
LOG_DIR = Path("/tmp/web_service_guard_demo_logs")
TEXT_LOG_PATH = LOG_DIR / "real_bug_repair_demo_full.log"
JSONL_LOG_PATH = LOG_DIR / "real_bug_repair_demo_events.jsonl"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(EditCodeTool())
    registry.register(BashTool())
    return registry


def _prepare_writable_fixture_copy() -> None:
    WRITABLE_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (WRITABLE_FIXTURE_DIR / "demo_webapp.py").write_text(
        (SOURCE_FIXTURE_DIR / "demo_webapp.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (WRITABLE_FIXTURE_DIR / "test_demo_webapp.py").write_text(
        (SOURCE_FIXTURE_DIR / "test_demo_webapp.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _append_text(text: str) -> None:
    with TEXT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def _append_event(event: dict[str, Any]) -> None:
    with JSONL_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_safe(event), ensure_ascii=False) + "\n")


def _reset_logs() -> None:
    _ensure_log_dir()
    TEXT_LOG_PATH.write_text("", encoding="utf-8")
    JSONL_LOG_PATH.write_text("", encoding="utf-8")


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


class LoggingLLMAdapter:
    """Wrap a real adapter and persist each completion turn."""

    def __init__(self, inner: OpenAICompatibleLLMAdapter, *, role: str) -> None:
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
    """Wrap the real AgentTool and log each invoke/execute payload/result."""

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


def capture_traceback() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(FIXTURE_DIR), "-p", "test_demo_webapp.py", "-v"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode == 0:
        raise RuntimeError("The demo test unexpectedly passed; the bug fixture is no longer failing.")
    return "\n".join(
        part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
    ).strip()


def rerun_tests() -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(FIXTURE_DIR), "-p", "test_demo_webapp.py", "-v"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    output = "\n".join(
        part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
    ).strip()
    return completed.returncode, output


def main() -> None:
    _reset_logs()
    _prepare_writable_fixture_copy()
    adapter = OpenAICompatibleLLMAdapter.from_env()
    _append_text(
        "=== ADAPTER CONFIG ===\n"
        f"base_url={adapter.base_url}\n"
        f"model={adapter.model}\n"
        f"timeout_sec={adapter.timeout_sec}\n"
        f"source_fixture_dir={SOURCE_FIXTURE_DIR}\n"
        f"writable_fixture_dir={WRITABLE_FIXTURE_DIR}\n"
    )
    _append_event(
        {
            "event": "adapter_config",
            "base_url": adapter.base_url,
            "model": adapter.model,
            "timeout_sec": adapter.timeout_sec,
            "source_fixture_dir": str(SOURCE_FIXTURE_DIR),
            "writable_fixture_dir": str(WRITABLE_FIXTURE_DIR),
        }
    )
    logging_main_adapter = LoggingLLMAdapter(adapter, role="main")
    logging_subagent_adapter = LoggingLLMAdapter(adapter, role="subagent")
    registry = build_registry()
    real_agent_tool = AgentTool(
        llm_adapter=logging_subagent_adapter,
        tool_registry=registry,
        default_max_turns=6,
    )
    logging_agent_tool = LoggingAgentTool(real_agent_tool)
    traceback = capture_traceback()

    print("=== CAPTURED TRACEBACK ===")
    print(traceback)
    _append_text("=== CAPTURED TRACEBACK ===\n" + traceback + "\n")
    _append_event({"event": "captured_traceback", "traceback": traceback})
    print("\n=== STARTING REAL ORCHESTRATOR RUN ===")

    result = run(
        {
            "run_id": "real-demo-run-001",
            "bug_event": {
                "service": "demo_webapp",
                "error": "ValueError",
                "entrypoint": str(FIXTURE_DIR / "demo_webapp.py"),
                "failing_test": str(TEST_FILE),
            },
            "traceback": traceback,
            "repo_root": str(REPO_ROOT),
            "branch": "demo",
            "max_iterations": 2,
        },
        llm_adapter=logging_main_adapter,
        agent_tool=logging_agent_tool,
        tool_registry=registry,
        default_agent_max_turns=6,
    )

    print("\n=== ORCHESTRATOR RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _append_text("\n=== ORCHESTRATOR RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _append_event({"event": "orchestrator_result", "result": result})

    test_returncode, test_output = rerun_tests()
    print("\n=== TEST STATUS AFTER RUN ===")
    print("returncode:", test_returncode)
    print(test_output)
    _append_text(
        "\n=== TEST STATUS AFTER RUN ===\n"
        f"returncode: {test_returncode}\n{test_output}\n"
    )
    _append_event(
        {
            "event": "post_run_test_status",
            "returncode": test_returncode,
            "output": test_output,
        }
    )
    print("\n=== LOG FILES ===")
    print(TEXT_LOG_PATH)
    print(JSONL_LOG_PATH)


if __name__ == "__main__":
    main()
