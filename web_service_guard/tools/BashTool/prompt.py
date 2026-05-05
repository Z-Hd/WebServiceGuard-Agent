"""Prompt and descriptive constants for BashTool."""

BASH_TOOL_NAME = "bash"
DESCRIPTION = "Execute a restricted shell command for testing or read-only inspection."

USAGE_NOTES = (
    "Executes a restricted shell command and returns its output.\n\n"
    "Usage:\n"
    f"- use `{BASH_TOOL_NAME}` when you need controlled shell execution for test commands or limited read-only inspection\n"
    f"- avoid using `{BASH_TOOL_NAME}` for file reading, file discovery, or content search when `read`, `glob`, or `grep` can do the job better\n"
    "- command must be a non-empty shell command string\n"
    "- working_dir defaults to the current working directory\n"
    "- timeout_sec defaults to 30 seconds\n"
    "- this tool is intended for test execution and constrained read-only shell usage, not arbitrary shell access\n"
    "- commands outside the runtime allowlist will be rejected\n"
    "- use this tool for commands such as test execution, `pwd`, `ls`, `cat`, `head`, `tail`, or simple echo-based checks when those commands are genuinely needed\n"
    "- on Windows, the corresponding read-only commands `cd`, `dir`, `type`, or `powershell Get-Content -Head/-Tail` are also allowed when appropriate\n"
    "- do not use this tool for file modification, dependency installation, git write operations, or any other state-changing command\n"
    "- for open-ended multi-step investigation, prefer the `agent` tool instead of trying to do the entire investigation through shell commands"
)
