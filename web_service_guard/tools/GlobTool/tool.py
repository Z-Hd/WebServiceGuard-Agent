"""File pattern matching tool aligned with Claude Code's Glob philosophy."""

from __future__ import annotations

from pathlib import Path
import glob as glob_module
from typing import Any

from errors import TOOL_READ_CODE_FAILED, make_error
from tools.base import BaseTool
from tools.GlobTool.prompt import DESCRIPTION, GLOB_TOOL_NAME, USAGE_NOTES


DEFAULT_HEAD_LIMIT = 100


class GlobTool(BaseTool):
    """Find files by glob pattern with stable structured output."""

    name = GLOB_TOOL_NAME
    description = f"{DESCRIPTION}\n\n{USAGE_NOTES}"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "head_limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
        "required": ["pattern"],
    }

    def execute(
        self,
        *,
        pattern: str,
        path: str | None = None,
        head_limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        result = self.execute_structured(
            pattern=pattern,
            path=path,
            head_limit=head_limit,
            offset=offset,
        )
        return self.format_structured_result(result)

    def execute_structured(
        self,
        *,
        pattern: str,
        path: str | None = None,
        head_limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        normalized_limit = DEFAULT_HEAD_LIMIT if head_limit is None else head_limit
        normalized_offset = 0 if offset is None else offset

        validation_error = self._validate_inputs(
            path=path,
            head_limit=normalized_limit,
            offset=normalized_offset,
        )
        if validation_error is not None:
            return validation_error

        base_path = Path(path).resolve() if path else Path.cwd()
        search_pattern = str(base_path / pattern)
        raw_matches = glob_module.glob(search_pattern, recursive=True)
        files = sorted(
            str(Path(match).resolve())
            for match in raw_matches
            if Path(match).is_file()
        )

        if normalized_limit == 0:
            sliced = files[normalized_offset:]
            truncated = False
            applied_limit = None
        else:
            sliced = files[normalized_offset: normalized_offset + normalized_limit]
            truncated = len(files) - normalized_offset > normalized_limit
            applied_limit = normalized_limit if truncated else None

        output = {
            "num_files": len(sliced),
            "filenames": sliced,
            "truncated": truncated,
            "applied_limit": applied_limit,
            "applied_offset": normalized_offset or None,
        }
        return {
            "status": "completed",
            "summary": self._build_summary(output),
            "output": output,
            "artifacts": sliced,
            "errors": [],
        }

    def _execute_structured(self, **kwargs: Any) -> dict[str, Any]:
        return self.execute_structured(**kwargs)

    def format_structured_result(self, result: dict[str, Any]) -> str:
        if result["status"] == "failed":
            return f"ERROR: {result['summary']}"
        output = result["output"]
        if not output["filenames"]:
            return "No files found"
        header = f"Found {output['num_files']} file(s)"
        body = "\n".join(output["filenames"])
        if output["truncated"]:
            body += "\n(Results are truncated. Consider using a more specific path or pattern.)"
        return f"{header}\n{body}"

    def _validate_inputs(
        self,
        *,
        path: str | None,
        head_limit: int,
        offset: int,
    ) -> dict[str, Any] | None:
        if head_limit < 0:
            return self._build_error(message=f"head_limit must be >= 0, got {head_limit}")
        if offset < 0:
            return self._build_error(message=f"offset must be >= 0, got {offset}")
        if path is None:
            return None
        candidate = Path(path)
        if not candidate.exists():
            return self._build_error(message=f"Directory does not exist: {path}")
        if not candidate.is_dir():
            return self._build_error(message=f"Path is not a directory: {path}")
        return None

    def _build_summary(self, output: dict[str, Any]) -> str:
        if output["num_files"] == 0:
            return "No files found"
        summary = f"Found {output['num_files']} file(s)"
        if output["truncated"]:
            summary += " (truncated)"
        return summary

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
                    stage="GLOB",
                    source="GlobTool",
                )
            ],
        }
