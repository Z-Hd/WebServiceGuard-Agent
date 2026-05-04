"""Prompt and descriptive constants for GlobTool."""

GLOB_TOOL_NAME = "glob"
DESCRIPTION = "Find files by glob pattern."

USAGE_NOTES = (
    "Usage:\n"
    f"- use `{GLOB_TOOL_NAME}` when you need to find files by name or path pattern\n"
    "- supports glob patterns such as `*.py`, `**/*.md`, or `src/**/*.ts`\n"
    "- path may point to a directory; if omitted, current working directory is searched\n"
    "- returns matching file paths only\n"
    "- head_limit defaults to 100 and may be set to 0 for unlimited results\n"
    "- offset skips the first N matched file paths before head_limit is applied\n"
    "- when you need multiple rounds of globbing, grepping, and synthesis, use the `agent` tool instead of treating this as the entire investigation"
)
