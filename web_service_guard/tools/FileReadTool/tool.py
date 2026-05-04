"""Text-file read tool aligned with Claude Code's Read tool philosophy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from errors import TOOL_READ_CODE_FAILED, make_error
from tools.base import BaseTool
from tools.FileReadTool.prompt import DESCRIPTION, FILE_READ_TOOL_NAME, USAGE_NOTES


DEFAULT_LINE_LIMIT = 200
MAX_LINE_LIMIT = 2000

BLOCKED_DEVICE_PATHS = {
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/full",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/tty",
    "/dev/console",
    "/dev/fd/0",
    "/dev/fd/1",
    "/dev/fd/2",
}


class FileReadTool(BaseTool):
    """Read a text file from disk with stable structured output."""

    name = FILE_READ_TOOL_NAME
    description = f"{DESCRIPTION}\n\n{USAGE_NOTES}"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
        "required": ["file_path"],
    }

    def execute(
        self,
        *,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
        tool_use_context: Any | None = None,
    ) -> str:
        result = self.execute_structured(
            file_path=file_path,
            offset=offset,
            limit=limit,
            tool_use_context=tool_use_context,
        )
        return self.format_structured_result(result)

    def execute_structured(
        self,
        *,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None,
        tool_use_context: Any | None = None,
    ) -> dict[str, Any]:
        normalized_offset = 1 if offset is None else offset
        normalized_limit = DEFAULT_LINE_LIMIT if limit is None else limit

        validation_error = self._validate_inputs(
            file_path=file_path,
            offset=normalized_offset,
            limit=normalized_limit,
        )
        if validation_error is not None:
            return validation_error

        path = Path(file_path)
        try:
            if path.is_dir():
                return self._build_error(
                    message=f"Path is a directory, not a file: {file_path}",
                )

            raw = path.read_bytes()
            if b"\x00" in raw:
                return self._build_error(
                    message=f"Binary file is not supported: {file_path}",
                )

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return self._build_error(
                    message=f"File is not valid UTF-8 text: {file_path}",
                )
        except FileNotFoundError:
            return self._build_error(message=f"File does not exist: {file_path}")
        except OSError as exc:
            return self._build_error(message=f"Failed to read file: {exc}")

        lines = text.splitlines()
        start_index = normalized_offset - 1
        end_index = start_index + min(normalized_limit, MAX_LINE_LIMIT)
        selected_lines = lines[start_index:end_index]
        content = "\n".join(selected_lines)
        truncated = len(lines) > end_index
        start_line = normalized_offset if lines else None
        end_line = normalized_offset + len(selected_lines) - 1 if selected_lines else None
        summary = (
            f"Read {len(selected_lines)} line(s) from {file_path}"
            + (" (truncated)" if truncated else "")
        )
        if tool_use_context is not None:
            try:
                mtime_ns = path.stat().st_mtime_ns
                tool_use_context.read_files[file_path] = {
                    "content": text,
                    "mtime_ns": mtime_ns,
                }
            except OSError:
                pass
        return {
            "status": "completed",
            "summary": summary,
            "output": {
                "file": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "content": content,
                "line_count": len(selected_lines),
            },
            "artifacts": [file_path],
            "errors": [],
        }

    def _execute_structured(self, **kwargs: Any) -> dict[str, Any]:
        return self.execute_structured(**kwargs)

    def format_structured_result(self, result: dict[str, Any]) -> str:
        if result["status"] == "failed":
            return f"ERROR: {result['summary']}"
        output = result["output"]
        header = (
            f"Read file: {output['file']} "
            f"(lines {output['start_line']}-{output['end_line']}, "
            f"returned {output['line_count']} lines)"
        )
        content = output["content"]
        return f"{header}\n{content}" if content else header
    def _validate_inputs(
        self,
        *,
        file_path: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any] | None:
        if not Path(file_path).is_absolute():
            return self._build_error(
                message=f"file_path must be absolute: {file_path}",
            )
        if file_path in BLOCKED_DEVICE_PATHS:
            return self._build_error(
                message=f"Reading device path is not allowed: {file_path}",
            )
        if offset < 1:
            return self._build_error(
                message=f"offset must be >= 1, got {offset}",
            )
        if limit < 1:
            return self._build_error(
                message=f"limit must be >= 1, got {limit}",
            )
        return None

    def _build_error(self, *, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "summary": message,
            "output": {},
            "artifacts": [],
            "errors": [
                make_error(
                    code=TOOL_READ_CODE_FAILED,
                    message=message,
                    retryable=False,
                    stage="READ",
                    source="FileReadTool",
                )
            ],
        }
