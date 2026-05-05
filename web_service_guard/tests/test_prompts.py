"""Tests for centralized second-stage prompt builders."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.orchestrator import (
    build_orchestrator_guardrail_feedback,
    build_orchestrator_initial_messages,
    build_orchestrator_system_prompt,
)
from prompts.agent_tool import build_agent_tool_description
from agents.registry import BUILTIN_AGENTS
from prompts.subagents import (
    build_execute_system_prompt,
    build_explore_system_prompt,
    build_plan_system_prompt,
    build_verify_system_prompt,
)
from tools.BashTool.prompt import BASH_TOOL_NAME
from tools.EditCodeTool.prompt import EDIT_CODE_TOOL_NAME, USAGE_NOTES as EDIT_USAGE_NOTES
from tools.FileReadTool.prompt import (
    DEFAULT_LINES_TO_READ,
    FILE_READ_TOOL_NAME,
    MAX_LINES_TO_READ,
    OFFSET_INSTRUCTION_DEFAULT,
    OFFSET_INSTRUCTION_TARGETED,
    USAGE_NOTES as FILE_READ_USAGE_NOTES,
)
from tools.GlobTool.prompt import GLOB_TOOL_NAME, USAGE_NOTES as GLOB_USAGE_NOTES
from tools.GrepTool.prompt import GREP_TOOL_NAME, USAGE_NOTES as GREP_USAGE_NOTES


def test_orchestrator_system_prompt_mentions_agent_only_coordination() -> None:
    prompt = build_orchestrator_system_prompt()

    assert "Repair Orchestrator" in prompt
    assert "using only the `agent` tool" in prompt
    assert "READY_FOR_PR" in prompt


def test_orchestrator_initial_messages_include_bug_event_and_traceback() -> None:
    messages = build_orchestrator_initial_messages(
        {
            "run_id": "run-001",
            "repo_root": "demo-repo",
            "branch": "main",
            "max_iterations": 3,
            "bug_event": {"service": "demo", "error": "ValueError"},
            "traceback": "Traceback: boom",
        },
        default_max_iterations=5,
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "run_id: run-001" in str(messages[1]["content"])
    assert "Traceback: boom" in str(messages[1]["content"])


def test_orchestrator_guardrail_feedback_is_user_message() -> None:
    message = build_orchestrator_guardrail_feedback("Do not call execute first.")

    assert message["role"] == "user"
    assert "Guardrail feedback:" in str(message["content"])
    assert "Do not call execute first." in str(message["content"])


def test_subagent_prompts_are_exposed_from_central_module() -> None:
    explore_prompt = build_explore_system_prompt()
    assert "file search and code exploration specialist" in explore_prompt
    assert "READ-ONLY MODE" in explore_prompt
    assert "Your strengths:" in explore_prompt
    assert "Guidelines:" in explore_prompt
    assert f"`{GLOB_TOOL_NAME}`" in explore_prompt
    assert f"`{GREP_TOOL_NAME}`" in explore_prompt
    assert f"`{FILE_READ_TOOL_NAME}`" in explore_prompt
    assert f"`{BASH_TOOL_NAME}`" in explore_prompt
    assert "NOTE: You are a fast exploration agent." in explore_prompt
    assert "A high-quality final answer should prioritize" in explore_prompt
    plan_prompt = build_plan_system_prompt()
    assert "software architect and planning specialist" in plan_prompt
    assert "=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===" in plan_prompt
    assert "## Your Process" in plan_prompt
    assert "## Required Output" in plan_prompt
    assert f"`{FILE_READ_TOOL_NAME}`" in plan_prompt
    assert f"`{GLOB_TOOL_NAME}`" in plan_prompt
    assert f"`{GREP_TOOL_NAME}`" in plan_prompt
    assert f"`{BASH_TOOL_NAME}`" in plan_prompt
    assert "You can only explore and plan." in plan_prompt
    execute_prompt = build_execute_system_prompt()
    assert "precision implementation agent" in execute_prompt
    assert "=== CRITICAL: MINIMAL, CONTROLLED EDITS ONLY ===" in execute_prompt
    assert f"`{FILE_READ_TOOL_NAME}`" in execute_prompt
    assert f"`{EDIT_CODE_TOOL_NAME}`" in execute_prompt
    assert "Always use" in execute_prompt
    assert "Perform broad refactors" in execute_prompt
    assert "Complete the implementation fully when the path is clear" in execute_prompt
    verify_prompt = build_verify_system_prompt()
    assert "You are a verification specialist." in verify_prompt
    assert "=== CRITICAL: DO NOT MODIFY THE PROJECT ===" in verify_prompt
    assert f"`{BASH_TOOL_NAME}`" in verify_prompt
    assert f"`{FILE_READ_TOOL_NAME}`" in verify_prompt
    assert f"`{GREP_TOOL_NAME}`" in verify_prompt
    assert f"`{GLOB_TOOL_NAME}`" in verify_prompt
    assert "=== RECOGNIZE YOUR OWN RATIONALIZATIONS ===" in verify_prompt
    assert "=== OUTPUT FORMAT (REQUIRED) ===" in verify_prompt
    assert "A successful primary verification command should normally trigger final reporting" in verify_prompt
    assert "Once those required successful checks are in hand, stop and issue the final report immediately" in verify_prompt
    assert "VERDICT: PASS" in verify_prompt
    assert "VERDICT: FAIL" in verify_prompt
    assert "VERDICT: PARTIAL" in verify_prompt


def test_agent_tool_description_explains_agent_selection_workflow() -> None:
    description = build_agent_tool_description(BUILTIN_AGENTS.values())

    assert "The `agent` tool is the only tool the main Repair Orchestrator should call directly." in description
    assert "When NOT to use the `agent` tool:" in description
    assert "## Writing the prompt" in description
    assert "## Agent selection guidance" in description
    assert "Never delegate understanding." in description
    assert "- explore:" in description
    assert "- plan:" in description
    assert "- execute:" in description
    assert "- verify:" in description
    assert "Choose the next agent based on what information is missing right now, not on a fixed sequence." in description


def test_grep_tool_prompt_matches_current_runtime_capabilities() -> None:
    assert f"ALWAYS use `{GREP_TOOL_NAME}` for search tasks." in GREP_USAGE_NOTES
    assert f"NEVER invoke `grep` or `rg` through `{BASH_TOOL_NAME}`" in GREP_USAGE_NOTES
    assert "output_mode=`content`" in GREP_USAGE_NOTES
    assert "output_mode=`files_with_matches`" in GREP_USAGE_NOTES
    assert "output_mode=`count`" in GREP_USAGE_NOTES
    assert "use the `agent` tool for open-ended investigations" in GREP_USAGE_NOTES


def test_glob_tool_prompt_matches_current_runtime_capabilities() -> None:
    assert f"use `{GLOB_TOOL_NAME}` when you need to find files by name or path pattern" in GLOB_USAGE_NOTES
    assert "supports glob patterns such as" in GLOB_USAGE_NOTES
    assert "returns matching file paths only" in GLOB_USAGE_NOTES
    assert "use the `agent` tool instead" in GLOB_USAGE_NOTES


def test_file_read_tool_prompt_matches_current_runtime_capabilities() -> None:
    assert "Reads a file from the local filesystem." in FILE_READ_USAGE_NOTES
    assert "The file_path parameter must be an absolute path" in FILE_READ_USAGE_NOTES
    assert f"By default, it reads up to {DEFAULT_LINES_TO_READ} lines" in FILE_READ_USAGE_NOTES
    assert OFFSET_INSTRUCTION_DEFAULT in FILE_READ_USAGE_NOTES
    assert OFFSET_INSTRUCTION_TARGETED in FILE_READ_USAGE_NOTES
    assert "offset is 1-based and defaults to 1" in FILE_READ_USAGE_NOTES
    assert f"limit is capped at {MAX_LINES_TO_READ} lines" in FILE_READ_USAGE_NOTES
    assert f"use a read-only `ls` command via `{BASH_TOOL_NAME}`" in FILE_READ_USAGE_NOTES


def test_bash_tool_prompt_matches_current_runtime_capabilities() -> None:
    from tools.BashTool.prompt import USAGE_NOTES as BASH_USAGE_NOTES

    assert f"use `{BASH_TOOL_NAME}` when you need controlled shell execution" in BASH_USAGE_NOTES
    assert "avoid using `bash` for file reading, file discovery, or content search" in BASH_USAGE_NOTES
    assert "commands outside the runtime allowlist will be rejected" in BASH_USAGE_NOTES
    assert "do not use this tool for file modification, dependency installation, git write operations" in BASH_USAGE_NOTES
    assert "prefer the `agent` tool instead" in BASH_USAGE_NOTES


def test_edit_tool_prompt_matches_current_runtime_capabilities() -> None:
    assert "Performs exact string replacements in files." in EDIT_USAGE_NOTES
    assert f"You must use `{FILE_READ_TOOL_NAME}` at least once" in EDIT_USAGE_NOTES
    assert "file_path must be an absolute path" in EDIT_USAGE_NOTES
    assert "old_string must match the current file content exactly" in EDIT_USAGE_NOTES
    assert "the edit will fail if old_string is not unique" in EDIT_USAGE_NOTES
    assert "use the smallest old_string that is clearly unique" in EDIT_USAGE_NOTES
    assert "use replace_all=true" in EDIT_USAGE_NOTES
