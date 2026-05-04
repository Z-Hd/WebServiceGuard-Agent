"""Prompt and descriptive constants for BashTool."""

BASH_TOOL_NAME = "bash"
DESCRIPTION = "Execute a restricted shell command for testing or read-only inspection."

USAGE_NOTES = (
    "Usage:\n"
    "- command must be a non-empty shell command string\n"
    "- working_dir defaults to the current working directory\n"
    "- timeout_sec defaults to 30 seconds\n"
    "- this tool is intended for read-only inspection and test execution, not arbitrary shell access"
)
