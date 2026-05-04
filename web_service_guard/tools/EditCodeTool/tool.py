"""Text edit tool aligned with Claude Code's Edit philosophy."""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path
from typing import Any

from errors import EXECUTE_PATCH_APPLY_FAILED, TOOL_EDIT_CODE_FAILED, make_error
from runtime.runtime_state import ToolUseContext
from tools.base import BaseTool
from tools.EditCodeTool.prompt import DESCRIPTION, EDIT_CODE_TOOL_NAME, USAGE_NOTES


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


class EditCodeTool(BaseTool):
    """Apply safe exact-string edits to an existing text file."""

    name = EDIT_CODE_TOOL_NAME
    description = f"{DESCRIPTION}\n\n{USAGE_NOTES}"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def execute(
        self,
        *,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool | None = None,
        tool_use_context: ToolUseContext | None = None,
    ) -> str:
        result = self.execute_structured(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            tool_use_context=tool_use_context,
        )
        return self.format_structured_result(result)

    def execute_structured(
        self,
        *,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool | None = None,
        tool_use_context: ToolUseContext | None = None,
    ) -> dict[str, Any]:
        replace_all = False if replace_all is None else replace_all
        validation_error = self._validate_inputs(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
        )
        if validation_error is not None:
            return validation_error

        path = Path(file_path)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"File does not exist: {file_path}",
            )
        except OSError as exc:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"Failed to read file: {exc}",
            )

        if b"\x00" in raw:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"Binary file is not supported: {file_path}",
            )

        try:
            current_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"File is not valid UTF-8 text: {file_path}",
            )

        current_mtime = path.stat().st_mtime_ns
        read_guard_error = self._validate_read_guard(
            path,
            tool_use_context,
            current_text=current_text,
            current_mtime=current_mtime,
        )
        if read_guard_error is not None:
            return read_guard_error

        match_count = current_text.count(old_string)
        if match_count == 0:
            return self._build_error(
                code=EXECUTE_PATCH_APPLY_FAILED,
                message="Target string was not found. Provide a more accurate old_string.",
            )
        if match_count > 1 and not replace_all:
            return self._build_error(
                code=EXECUTE_PATCH_APPLY_FAILED,
                message="Target string is not unique. Provide a more unique old_string or set replace_all=True.",
            )

        if replace_all:
            updated_text = current_text.replace(old_string, new_string)
        else:
            updated_text = current_text.replace(old_string, new_string, 1)

        path.write_text(updated_text, encoding="utf-8")
        diff_lines = list(
            unified_diff(
                current_text.splitlines(),
                updated_text.splitlines(),
                fromfile=file_path,
                tofile=file_path,
                lineterm="",
            )
        )
        lines_added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        lines_removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        diff_summary = diff_lines[:20]

        return {
            "status": "completed",
            "summary": f"Applied edit to {file_path}",
            "output": {
                "modified_file": file_path,
                "diff_summary": diff_summary,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
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
        summary = (
            f"Edited file: {output['modified_file']} "
            f"(+{output['lines_added']} / -{output['lines_removed']})"
        )
        details = "\n".join(output["diff_summary"])
        return f"{summary}\n{details}" if details else summary

    def _validate_inputs(
        self,
        *,
        file_path: str,
        old_string: str,
        new_string: str,
    ) -> dict[str, Any] | None:
        path = Path(file_path)
        if not path.is_absolute():
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"file_path must be absolute: {file_path}",
            )
        if file_path in BLOCKED_DEVICE_PATHS:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"Editing device path is not allowed: {file_path}",
            )
        if path.exists() and path.is_dir():
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message=f"Path is a directory, not a file: {file_path}",
            )
        if old_string == "":
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="old_string must not be empty.",
            )
        if old_string == new_string:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="old_string and new_string are identical; no edit is needed.",
            )
        return None

    def _validate_read_guard(
        self,
        path: Path,
        tool_use_context: ToolUseContext | None,
        *,
        current_text: str,
        current_mtime: int,
    ) -> dict[str, Any] | None:
        if tool_use_context is None:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="File must be read before editing.",
            )

        read_entry = tool_use_context.read_files.get(str(path))
        if read_entry is None:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="File must be read before editing.",
            )

        if current_mtime != read_entry["mtime_ns"]:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="File changed after it was read. Read it again before editing.",
            )
        if current_text != read_entry["content"]:
            return self._build_error(
                code=TOOL_EDIT_CODE_FAILED,
                message="File content changed after it was read. Read it again before editing.",
            )
        return None

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
                    stage="EDIT",
                    source="EditCodeTool",
                )
            ],
        }
