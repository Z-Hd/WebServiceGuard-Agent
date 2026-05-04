"""Prompt and descriptive constants for GlobTool."""

GLOB_TOOL_NAME = "glob"
DESCRIPTION = "Find files by glob pattern."

USAGE_NOTES = (
    "Usage:\n"
    "- pattern must be a valid glob pattern such as '*.py' or '**/*.md'\n"
    "- path may point to a directory; if omitted, current working directory is searched\n"
    "- head_limit defaults to 100 and may be set to 0 for unlimited results\n"
    "- offset skips the first N matched file paths before head_limit is applied"
)
