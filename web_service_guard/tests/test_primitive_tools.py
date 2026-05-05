"""Tests for Primitive Tool contracts and low-level execution semantics."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.runtime_state import ToolUseContext
from tools.BashTool import BashTool
from tools.EditCodeTool import EditCodeTool
from tools.FileReadTool import FileReadTool
from tools.GrepTool import GrepTool
from tools.GlobTool import GlobTool


def test_file_read_tool_reads_whole_text_file(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("line1\nline2\nline3\n", encoding="utf-8")

    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(file_path))

    assert result["status"] == "completed"
    assert result["output"]["file"] == str(file_path)
    assert result["output"]["content"] == "line1\nline2\nline3"
    assert result["output"]["start_line"] == 1
    assert result["output"]["end_line"] == 3


def test_file_read_tool_reads_line_range(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("a\nb\nc\nd\n", encoding="utf-8")

    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(file_path), offset=2, limit=2)

    assert result["status"] == "completed"
    assert result["output"]["content"] == "b\nc"
    assert result["output"]["start_line"] == 2
    assert result["output"]["end_line"] == 3


def test_file_read_tool_records_content_in_tool_context(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nbeta\n", encoding="utf-8")
    context = ToolUseContext()

    result = FileReadTool()._execute_structured(
        file_path=str(file_path),
        tool_use_context=context,
    )

    assert result["status"] == "completed"
    assert str(file_path) in context.read_files
    assert context.read_files[str(file_path)]["content"] == "alpha\nbeta\n"


def test_file_read_tool_rejects_non_absolute_path() -> None:
    tool = FileReadTool()
    result = tool._execute_structured(file_path="relative.txt")

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "TOOL_READ_CODE_FAILED"


def test_file_read_tool_rejects_missing_file(tmp_path: Path) -> None:
    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(tmp_path / "missing.txt"))

    assert result["status"] == "failed"
    assert "does not exist" in result["summary"]


def test_file_read_tool_rejects_directory(tmp_path: Path) -> None:
    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(tmp_path))

    assert result["status"] == "failed"
    assert "directory" in result["summary"]


def test_file_read_tool_allows_empty_file(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.txt"
    file_path.write_text("", encoding="utf-8")

    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(file_path))

    assert result["status"] == "completed"
    assert result["output"]["content"] == ""
    assert result["output"]["line_count"] == 0


def test_file_read_tool_truncates_to_default_limit(tmp_path: Path) -> None:
    file_path = tmp_path / "many_lines.txt"
    file_path.write_text("\n".join(f"line-{i}" for i in range(250)), encoding="utf-8")

    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(file_path))

    assert result["status"] == "completed"
    assert result["output"]["line_count"] == 200
    assert "truncated" in result["summary"]


def test_file_read_tool_rejects_binary_file(tmp_path: Path) -> None:
    file_path = tmp_path / "binary.bin"
    file_path.write_bytes(b"\x00\x01\x02")

    tool = FileReadTool()
    result = tool._execute_structured(file_path=str(file_path))

    assert result["status"] == "failed"
    assert "Binary file" in result["summary"]


def test_grep_tool_matches_single_file(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nbeta\nalpha beta\n", encoding="utf-8")

    tool = GrepTool()
    result = tool._execute_structured(pattern="alpha", path=str(file_path), output_mode="content")

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 1
    assert "alpha" in result["output"]["content"]


def test_grep_tool_matches_directory_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("match here\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("also match\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("nope\n", encoding="utf-8")

    tool = GrepTool()
    result = tool._execute_structured(pattern="match", path=str(tmp_path), output_mode="files_with_matches")

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 2


def test_grep_tool_respects_glob_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("match here\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("match here\n", encoding="utf-8")

    tool = GrepTool()
    result = tool._execute_structured(
        pattern="match",
        path=str(tmp_path),
        glob="*.py",
        output_mode="files_with_matches",
    )

    assert result["status"] == "completed"
    assert result["output"]["filenames"] == [str(tmp_path / "a.py")]


def test_grep_tool_count_mode(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("a\nmatch\nmatch again\n", encoding="utf-8")

    tool = GrepTool()
    result = tool._execute_structured(pattern="match", path=str(file_path), output_mode="count")

    assert result["status"] == "completed"
    assert result["output"]["num_matches"] == 2


def test_grep_tool_rejects_invalid_regex(tmp_path: Path) -> None:
    tool = GrepTool()
    result = tool._execute_structured(pattern="(", path=str(tmp_path))

    assert result["status"] == "failed"
    assert "Invalid regex pattern" in result["summary"]


def test_grep_tool_path_missing(tmp_path: Path) -> None:
    tool = GrepTool()
    result = tool._execute_structured(pattern="match", path=str(tmp_path / "missing"))

    assert result["status"] == "failed"
    assert "does not exist" in result["summary"]


def test_grep_tool_head_limit_and_offset(tmp_path: Path) -> None:
    for idx in range(5):
        (tmp_path / f"{idx}.txt").write_text("match\n", encoding="utf-8")

    tool = GrepTool()
    result = tool._execute_structured(
        pattern="match",
        path=str(tmp_path),
        output_mode="files_with_matches",
        head_limit=2,
        offset=1,
    )

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 2
    assert result["output"]["applied_offset"] == 1


def test_glob_tool_matches_single_directory_level(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="*.py", path=str(tmp_path))

    assert result["status"] == "completed"
    assert result["output"]["filenames"] == [str((tmp_path / "a.py").resolve())]


def test_glob_tool_matches_recursively(tmp_path: Path) -> None:
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.py").write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="**/*.py", path=str(tmp_path))

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 2


def test_glob_tool_rejects_missing_directory(tmp_path: Path) -> None:
    tool = GlobTool()
    result = tool._execute_structured(pattern="*.py", path=str(tmp_path / "missing"))

    assert result["status"] == "failed"
    assert "does not exist" in result["summary"]


def test_glob_tool_rejects_file_as_path(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="*.txt", path=str(file_path))

    assert result["status"] == "failed"
    assert "not a directory" in result["summary"]


def test_glob_tool_head_limit_and_offset(tmp_path: Path) -> None:
    for idx in range(5):
        (tmp_path / f"{idx}.py").write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="*.py", path=str(tmp_path), head_limit=2, offset=1)

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 2
    assert result["output"]["applied_offset"] == 1


def test_glob_tool_zero_head_limit_returns_all_remaining_files(tmp_path: Path) -> None:
    for idx in range(3):
        (tmp_path / f"{idx}.py").write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="*.py", path=str(tmp_path), head_limit=0, offset=1)

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 2
    assert result["output"]["applied_limit"] is None


def test_glob_tool_returns_empty_result_when_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    tool = GlobTool()
    result = tool._execute_structured(pattern="*.py", path=str(tmp_path))

    assert result["status"] == "completed"
    assert result["output"]["num_files"] == 0


def test_edit_code_tool_replaces_unique_match(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello world\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)

    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="world",
        new_string="agent",
        tool_use_context=context,
    )

    assert result["status"] == "completed"
    assert "agent" in file_path.read_text(encoding="utf-8")
    assert result["output"]["modified_file"] == str(file_path)


def test_edit_code_tool_allows_second_edit_after_first_edit_updates_read_state(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha world\nbeta line\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)
    tool = EditCodeTool()

    first = tool._execute_structured(
        file_path=str(file_path),
        old_string="world",
        new_string="agent",
        tool_use_context=context,
    )
    assert first["status"] == "completed"

    second = tool._execute_structured(
        file_path=str(file_path),
        old_string="beta",
        new_string="gamma",
        tool_use_context=context,
    )
    assert second["status"] == "completed"
    assert file_path.read_text(encoding="utf-8") == "alpha agent\ngamma line\n"


def test_edit_code_tool_matches_normalized_read_state_keys(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello world\n", encoding="utf-8")
    context = ToolUseContext()
    canonical = str(file_path.resolve())
    alias_path = str(tmp_path / "." / "sample.txt")

    FileReadTool()._execute_structured(file_path=alias_path, tool_use_context=context)

    result = EditCodeTool()._execute_structured(
        file_path=canonical,
        old_string="world",
        new_string="agent",
        tool_use_context=context,
    )

    assert result["status"] == "completed"
    assert file_path.read_text(encoding="utf-8") == "hello agent\n"


def test_edit_code_tool_rejects_multi_match_without_replace_all(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("x\nx\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)

    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="x",
        new_string="y",
        tool_use_context=context,
    )

    assert result["status"] == "failed"
    assert "not unique" in result["summary"]


def test_edit_code_tool_replace_all_multiple_matches(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("x\nx\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)

    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="x",
        new_string="y",
        replace_all=True,
        tool_use_context=context,
    )

    assert result["status"] == "completed"
    assert file_path.read_text(encoding="utf-8") == "y\ny\n"


def test_edit_code_tool_rejects_missing_old_string(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)

    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="world",
        new_string="agent",
        tool_use_context=context,
    )

    assert result["status"] == "failed"
    assert "not found" in result["summary"]


def test_edit_code_tool_rejects_file_not_read(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello\n", encoding="utf-8")
    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="hello",
        new_string="agent",
        tool_use_context=ToolUseContext(),
    )

    assert result["status"] == "failed"
    assert "must be read before editing" in result["summary"]


def test_edit_code_tool_rejects_when_file_changed_after_read(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)
    file_path.write_text("changed\n", encoding="utf-8")

    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="hello",
        new_string="agent",
        tool_use_context=context,
    )

    assert result["status"] == "failed"
    assert "changed after it was read" in result["summary"]


def test_edit_code_tool_rejects_non_absolute_path() -> None:
    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path="relative.txt",
        old_string="a",
        new_string="b",
        tool_use_context=ToolUseContext(),
    )

    assert result["status"] == "failed"


def test_edit_code_tool_rejects_directory_path(tmp_path: Path) -> None:
    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(tmp_path),
        old_string="a",
        new_string="b",
        tool_use_context=ToolUseContext(),
    )

    assert result["status"] == "failed"
    assert "directory" in result["summary"]


def test_edit_code_tool_rejects_binary_file(tmp_path: Path) -> None:
    file_path = tmp_path / "binary.bin"
    file_path.write_bytes(b"\x00\x01")
    context = ToolUseContext()
    context.read_files[str(file_path)] = {"content": "", "mtime_ns": file_path.stat().st_mtime_ns}
    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="a",
        new_string="b",
        tool_use_context=context,
    )

    assert result["status"] == "failed"
    assert "Binary file" in result["summary"]


def test_edit_code_tool_rejects_identical_old_and_new_string(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("same\n", encoding="utf-8")
    context = ToolUseContext()
    FileReadTool()._execute_structured(file_path=str(file_path), tool_use_context=context)
    tool = EditCodeTool()
    result = tool._execute_structured(
        file_path=str(file_path),
        old_string="same",
        new_string="same",
        tool_use_context=context,
    )

    assert result["status"] == "failed"


def test_bash_tool_executes_pwd() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="pwd")

    assert result["status"] == "completed"
    assert result["output"]["exit_code"] == 0
    assert result["output"]["stdout"].strip()


def test_bash_tool_captures_stdout() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="echo hello")

    assert result["status"] == "completed"
    assert "hello" in result["output"]["stdout"]


def test_bash_tool_allows_windows_dir_command() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="dir")

    assert result["status"] == "completed"
    assert result["output"]["exit_code"] == 0


def test_bash_tool_allows_windows_cd_command() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="cd")

    assert result["status"] == "completed"
    assert result["output"]["exit_code"] == 0


def test_bash_tool_allows_windows_type_command(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello\nworld\n", encoding="utf-8")

    tool = BashTool()
    result = tool._execute_structured(command=f"type {file_path}")

    assert result["status"] == "completed"
    assert "hello" in result["output"]["stdout"]


def test_bash_tool_allows_windows_powershell_head_tail_commands(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    tool = BashTool()
    head_result = tool._execute_structured(
        command=f'powershell -Command Get-Content "{file_path}" -Head 1'
    )
    tail_result = tool._execute_structured(
        command=f'powershell -Command Get-Content "{file_path}" -Tail 1'
    )

    assert head_result["status"] == "completed"
    assert tail_result["status"] == "completed"


def test_bash_tool_reports_nonzero_exit_code() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="python3 -m unittest definitely_missing_test_module")

    assert result["status"] == "failed"
    assert result["output"]["exit_code"] == 1


def test_bash_tool_allows_python_test_file_execution(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "import unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertEqual(1, 1)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    result = BashTool()._execute_structured(command=f"python3 {test_file}")

    assert result["status"] == "completed"
    assert result["output"]["exit_code"] == 0


def test_bash_tool_allows_python_inline_execution() -> None:
    result = BashTool()._execute_structured(command='python3 -c "print(123)"')

    assert result["status"] == "completed"
    assert result["output"]["stdout"].strip() == "123"


def test_bash_tool_allows_cd_then_python_execution(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "import unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertEqual(1, 1)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    result = BashTool()._execute_structured(command=f"cd {tmp_path} && python3 test_sample.py -v")

    assert result["status"] == "completed"
    assert result["output"]["exit_code"] == 0


def test_bash_tool_rejects_empty_command() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="   ")

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "TOOL_BASH_COMMAND_REJECTED"


def test_bash_tool_rejects_missing_working_dir(tmp_path: Path) -> None:
    tool = BashTool()
    result = tool._execute_structured(command="pwd", working_dir=str(tmp_path / "missing"))

    assert result["status"] == "failed"
    assert "does not exist" in result["summary"]


def test_bash_tool_rejects_file_as_working_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("x", encoding="utf-8")
    tool = BashTool()
    result = tool._execute_structured(command="pwd", working_dir=str(file_path))

    assert result["status"] == "failed"
    assert "not a directory" in result["summary"]


def test_bash_tool_rejects_denied_command() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="rm -rf /tmp/test")

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "TOOL_BASH_COMMAND_REJECTED"


def test_bash_tool_rejects_outside_allowlist_command() -> None:
    tool = BashTool()
    result = tool._execute_structured(command="whoami")

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "TOOL_BASH_COMMAND_REJECTED"


def test_bash_tool_rejects_cd_missing_directory_then_python(tmp_path: Path) -> None:
    result = BashTool()._execute_structured(
        command=f"cd {tmp_path / 'missing'} && python3 test_sample.py -v"
    )

    assert result["status"] == "failed"
    assert "outside the first-phase allowlist" in result["summary"]


def test_bash_tool_rejects_python_with_install_command() -> None:
    result = BashTool()._execute_structured(command="pip install pytest")

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "TOOL_BASH_COMMAND_REJECTED"
