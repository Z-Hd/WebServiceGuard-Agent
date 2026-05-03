"""Pure-text search tool aligned with Claude Code's Grep philosophy."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
import os
import re
from typing import Any

from errors import TOOL_READ_CODE_FAILED, make_error
from tools.base import BaseTool
from tools.GrepTool.prompt import DESCRIPTION, GREP_TOOL_NAME, USAGE_NOTES


DEFAULT_HEAD_LIMIT = 50
DEFAULT_OUTPUT_MODE = "files_with_matches"
SUPPORTED_OUTPUT_MODES = {"content", "files_with_matches", "count"}


class GrepTool(BaseTool):
    """Search text file contents with regex and stable structured output."""

    name = GREP_TOOL_NAME
    description = f"{DESCRIPTION}\n\n{USAGE_NOTES}"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "glob": {"type": "string"},
            "output_mode": {"type": "string"},
            "context_lines": {"type": "integer"},
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
        glob: str | None = None,
        output_mode: str | None = None,
        context_lines: int | None = None,
        head_limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        result = self.execute_structured(
            pattern=pattern,
            path=path,
            glob=glob,
            output_mode=output_mode,
            context_lines=context_lines,
            head_limit=head_limit,
            offset=offset,
        )
        return self.format_structured_result(result)

    def execute_structured(
        self,
        *,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        output_mode: str | None = None,
        context_lines: int | None = None,
        head_limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        mode = DEFAULT_OUTPUT_MODE if output_mode is None else output_mode
        normalized_context = 0 if context_lines is None else context_lines
        normalized_head_limit = DEFAULT_HEAD_LIMIT if head_limit is None else head_limit
        normalized_offset = 0 if offset is None else offset

        validation_error = self._validate_inputs(
            pattern=pattern,
            path=path,
            output_mode=mode,
            context_lines=normalized_context,
            head_limit=normalized_head_limit,
            offset=normalized_offset,
        )
        if validation_error is not None:
            return validation_error

        base_path = Path(path).resolve() if path else Path.cwd()
        targets = self._collect_targets(base_path, glob)
        regex = re.compile(pattern)

        file_matches: list[dict[str, Any]] = []
        for target in targets:
            try:
                raw = target.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            lines = text.splitlines()
            matches = self._match_lines(regex, lines, normalized_context)
            if matches:
                file_matches.append(
                    {
                        "file": str(target),
                        "matches": matches,
                    }
                )

        sliced_matches, applied_limit, applied_offset = self._slice_results(
            file_matches,
            normalized_head_limit,
            normalized_offset,
        )

        output = self._build_output(
            sliced_matches,
            file_matches,
            mode,
        )
        output["applied_limit"] = applied_limit
        output["applied_offset"] = applied_offset

        return {
            "status": "completed",
            "summary": self._build_summary(output),
            "output": output,
            "artifacts": output["filenames"],
            "errors": [],
        }

    def _execute_structured(self, **kwargs: Any) -> dict[str, Any]:
        return self.execute_structured(**kwargs)

    def format_structured_result(self, result: dict[str, Any]) -> str:
        if result["status"] == "failed":
            return f"ERROR: {result['summary']}"

        output = result["output"]
        mode = output["mode"]
        if mode == "files_with_matches":
            header = f"Found matches in {output['num_files']} file(s)"
            body = "\n".join(output["filenames"])
            return f"{header}\n{body}" if body else header
        if mode == "count":
            return f"Found {output['num_matches']} match(es) across {output['num_files']} file(s)"
        content = output.get("content") or ""
        header = f"Found matches in {output['num_files']} file(s)"
        return f"{header}\n{content}" if content else header

    def _validate_inputs(
        self,
        *,
        pattern: str,
        path: str | None,
        output_mode: str,
        context_lines: int,
        head_limit: int,
        offset: int,
    ) -> dict[str, Any] | None:
        try:
            re.compile(pattern)
        except re.error as exc:
            return self._build_error(message=f"Invalid regex pattern: {exc}")

        if output_mode not in SUPPORTED_OUTPUT_MODES:
            return self._build_error(message=f"Unsupported output_mode: {output_mode}")
        if context_lines < 0:
            return self._build_error(message=f"context_lines must be >= 0, got {context_lines}")
        if head_limit < 0:
            return self._build_error(message=f"head_limit must be >= 0, got {head_limit}")
        if offset < 0:
            return self._build_error(message=f"offset must be >= 0, got {offset}")
        if path is not None and not Path(path).exists():
            return self._build_error(message=f"Path does not exist: {path}")
        return None

    def _collect_targets(self, base_path: Path, glob: str | None) -> list[Path]:
        if base_path.is_file():
            return [base_path] if self._matches_glob(base_path, glob) else []

        targets: list[Path] = []
        for root, _, files in os.walk(base_path):
            for file_name in files:
                candidate = Path(root) / file_name
                if self._matches_glob(candidate, glob):
                    targets.append(candidate)
        return targets

    def _matches_glob(self, path: Path, glob: str | None) -> bool:
        if glob is None:
            return True
        return fnmatch(path.name, glob) or fnmatch(str(path), glob)

    def _match_lines(
        self,
        regex: re.Pattern[str],
        lines: list[str],
        context_lines: int,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            if regex.search(line):
                start = max(0, idx - context_lines)
                end = min(len(lines), idx + context_lines + 1)
                context = lines[start:end]
                matches.append(
                    {
                        "line_number": idx + 1,
                        "line": line,
                        "context": context,
                    }
                )
        return matches

    def _slice_results(
        self,
        matches: list[dict[str, Any]],
        head_limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int | None, int | None]:
        if head_limit == 0:
            return matches[offset:], None, offset or None
        sliced = matches[offset: offset + head_limit]
        applied_limit = head_limit if len(matches) - offset > head_limit else None
        applied_offset = offset or None
        return sliced, applied_limit, applied_offset

    def _build_output(
        self,
        sliced_matches: list[dict[str, Any]],
        all_matches: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        filenames = [entry["file"] for entry in sliced_matches]
        if mode == "files_with_matches":
            return {
                "mode": mode,
                "num_files": len(sliced_matches),
                "filenames": filenames,
                "content": None,
                "num_matches": None,
            }
        if mode == "count":
            total_matches = sum(len(entry["matches"]) for entry in sliced_matches)
            return {
                "mode": mode,
                "num_files": len(sliced_matches),
                "filenames": filenames,
                "content": None,
                "num_matches": total_matches,
            }

        blocks: list[str] = []
        for entry in sliced_matches:
            for match in entry["matches"]:
                context = "\n".join(match["context"])
                blocks.append(f"{entry['file']}:{match['line_number']}\n{context}")
        return {
            "mode": mode,
            "num_files": len(sliced_matches),
            "filenames": filenames,
            "content": "\n\n".join(blocks),
            "num_matches": sum(len(entry["matches"]) for entry in sliced_matches),
        }

    def _build_summary(self, output: dict[str, Any]) -> str:
        mode = output["mode"]
        if mode == "files_with_matches":
            return f"Found matches in {output['num_files']} file(s)"
        if mode == "count":
            return f"Found {output['num_matches']} match(es) across {output['num_files']} file(s)"
        return f"Collected content matches from {output['num_files']} file(s)"

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
                    stage="GREP",
                    source="GrepTool",
                )
            ],
        }
