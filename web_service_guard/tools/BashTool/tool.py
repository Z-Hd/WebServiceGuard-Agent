"""Minimal safe Bash tool aligned with Claude Code's verification needs."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import time
from typing import Any

from errors import (
    TOOL_BASH_COMMAND_REJECTED,
    TOOL_BASH_TIMEOUT,
    TOOL_RUN_TEST_FAILED,
    VERIFY_TEST_ENVIRONMENT_ERROR,
    make_error,
)
from tools.BashTool.prompt import BASH_TOOL_NAME, DESCRIPTION, USAGE_NOTES
from tools.base import BaseTool


DEFAULT_TIMEOUT_SEC = 30
READ_ONLY_COMMAND_PREFIXES = ("pwd", "ls", "cat", "head", "tail", "echo")
PYTHON_BINARIES = {"python", "python3"}
PYTHON_MODULE_TEST_RUNNERS = {"pytest", "unittest"}
SIMPLE_TEST_COMMANDS = ("pytest",)
NODE_TEST_PREFIXES = ("npm test", "npm run test", "make test")
CD_CHAIN_OPERATOR = "&&"
DENIED_PREFIXES = (
    "rm",
    "sudo",
    "chmod",
    "chown",
    "mv",
    "cp",
    "git push",
    "git commit",
)


class BashTool(BaseTool):
    """Execute a restricted shell command and return stable structured output."""

    name = BASH_TOOL_NAME
    description = f"{DESCRIPTION}\n\n{USAGE_NOTES}"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "working_dir": {"type": "string"},
            "timeout_sec": {"type": "integer"},
        },
        "required": ["command"],
    }

    def execute(
        self,
        *,
        command: str,
        working_dir: str | None = None,
        timeout_sec: int | None = None,
        tool_use_context: Any | None = None,
    ) -> str:
        result = self.execute_structured(
            command=command,
            working_dir=working_dir,
            timeout_sec=timeout_sec,
        )
        return self.format_structured_result(result)

    def execute_structured(
        self,
        *,
        command: str,
        working_dir: str | None = None,
        timeout_sec: int | None = None,
        tool_use_context: Any | None = None,
    ) -> dict[str, Any]:
        normalized_timeout = DEFAULT_TIMEOUT_SEC if timeout_sec is None else timeout_sec
        normalized_dir = str(Path.cwd() if working_dir is None else Path(working_dir).resolve())

        validation_error = self._validate_inputs(
            command=command,
            working_dir=normalized_dir,
            timeout_sec=normalized_timeout,
        )
        if validation_error is not None:
            return validation_error

        start = time.time()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=normalized_dir,
                capture_output=True,
                text=True,
                timeout=normalized_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return self._build_error(
                code=TOOL_BASH_TIMEOUT,
                message=f"Command timed out after {normalized_timeout} second(s): {command}",
            )
        except OSError as exc:
            return self._build_error(
                code=VERIFY_TEST_ENVIRONMENT_ERROR,
                message=f"Failed to execute command: {exc}",
            )

        duration_sec = time.time() - start
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        combined_output = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()

        if completed.returncode != 0:
            return {
                "status": "failed",
                "summary": f"Command exited with code {completed.returncode}: {command}",
                "output": {
                    "command": command,
                    "working_dir": normalized_dir,
                    "exit_code": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "combined_output": combined_output,
                    "duration_sec": duration_sec,
                },
                "artifacts": [],
                "errors": [
                    make_error(
                        code=TOOL_RUN_TEST_FAILED,
                        message=f"Command exited with code {completed.returncode}: {command}",
                        retryable=False,
                        stage="BASH",
                        source="BashTool",
                    )
                ],
            }

        return {
            "status": "completed",
            "summary": f"Command completed successfully: {command}",
            "output": {
                "command": command,
                "working_dir": normalized_dir,
                "exit_code": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "combined_output": combined_output,
                "duration_sec": duration_sec,
            },
            "artifacts": [],
            "errors": [],
        }

    def _execute_structured(self, **kwargs: Any) -> dict[str, Any]:
        return self.execute_structured(**kwargs)

    def format_structured_result(self, result: dict[str, Any]) -> str:
        if result["status"] == "failed":
            return f"ERROR: {result['summary']}"
        output = result["output"]
        return (
            f"Command: {output['command']}\n"
            f"Exit code: {output['exit_code']}\n"
            f"STDOUT:\n{output['stdout']}\n"
            f"STDERR:\n{output['stderr']}"
        ).strip()

    def _validate_inputs(
        self,
        *,
        command: str,
        working_dir: str,
        timeout_sec: int,
    ) -> dict[str, Any] | None:
        command = command.strip()
        if not command:
            return self._build_error(
                code=TOOL_BASH_COMMAND_REJECTED,
                message="command must not be empty.",
            )
        if timeout_sec <= 0:
            return self._build_error(
                code=TOOL_BASH_COMMAND_REJECTED,
                message=f"timeout_sec must be > 0, got {timeout_sec}",
            )
        workdir_path = Path(working_dir)
        if not workdir_path.exists():
            return self._build_error(
                code=VERIFY_TEST_ENVIRONMENT_ERROR,
                message=f"Working directory does not exist: {working_dir}",
            )
        if not workdir_path.is_dir():
            return self._build_error(
                code=VERIFY_TEST_ENVIRONMENT_ERROR,
                message=f"Working directory is not a directory: {working_dir}",
            )
        lowered = command.lower()
        if any(lowered.startswith(prefix) for prefix in DENIED_PREFIXES):
            return self._build_error(
                code=TOOL_BASH_COMMAND_REJECTED,
                message=f"Command is not allowed: {command}",
            )
        if not self._is_allowed_command(command, workdir_path):
            return self._build_error(
                code=TOOL_BASH_COMMAND_REJECTED,
                message=f"Command is outside the first-phase allowlist: {command}",
            )
        return None

    def _is_allowed_command(self, command: str, working_dir: Path) -> bool:
        command = command.strip()
        if not command:
            return False

        if self._contains_denied_segment(command):
            return False

        if CD_CHAIN_OPERATOR in command:
            left, right = command.split(CD_CHAIN_OPERATOR, 1)
            left = left.strip()
            right = right.strip()
            if not left.startswith("cd "):
                return False
            target_dir = left[3:].strip()
            if not target_dir:
                return False
            resolved_dir = (working_dir / target_dir).resolve() if not Path(target_dir).is_absolute() else Path(target_dir).resolve()
            if not resolved_dir.exists() or not resolved_dir.is_dir():
                return False
            return self._is_allowed_command(right, resolved_dir)

        return self._is_allowed_simple_command(command)

    def _contains_denied_segment(self, command: str) -> bool:
        segments = [segment.strip() for segment in command.split(CD_CHAIN_OPERATOR)]
        return any(self._starts_with_denied_prefix(segment) for segment in segments if segment)

    def _starts_with_denied_prefix(self, command: str) -> bool:
        lowered = command.lower()
        return any(lowered.startswith(prefix) for prefix in DENIED_PREFIXES)

    def _is_allowed_simple_command(self, command: str) -> bool:
        lowered = command.lower()
        if any(lowered.startswith(prefix) for prefix in READ_ONLY_COMMAND_PREFIXES):
            return True
        if any(lowered.startswith(prefix) for prefix in NODE_TEST_PREFIXES):
            return True
        if any(lowered.startswith(prefix) for prefix in SIMPLE_TEST_COMMANDS):
            return True

        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        if not parts:
            return False

        executable = parts[0]
        if executable in PYTHON_BINARIES:
            if len(parts) >= 3 and parts[1] == "-m" and parts[2] in PYTHON_MODULE_TEST_RUNNERS:
                return True
            if len(parts) >= 3 and parts[1] == "-c":
                return True
            if len(parts) >= 2:
                script = parts[1]
                return script.endswith(".py")
        return False

    def _build_error(self, *, code: str, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "summary": message,
            "output": {},
            "artifacts": [],
            "errors": [
                make_error(
                    code=code,
                    message=message,
                    retryable=False,
                    stage="BASH",
                    source="BashTool",
                )
            ],
        }
