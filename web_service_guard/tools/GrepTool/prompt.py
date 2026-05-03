"""Prompt and descriptive constants for GrepTool."""

GREP_TOOL_NAME = "grep"
DESCRIPTION = "Search text file contents using regular expressions."

USAGE_NOTES = (
    "Usage:\n"
    "- pattern must be a valid regular expression\n"
    "- path may point to a file or directory; if omitted, current working directory is searched\n"
    "- output_mode defaults to 'files_with_matches'\n"
    "- context_lines is only meaningful in 'content' mode\n"
    "- head_limit defaults to 50 and may be set to 0 for unlimited results\n"
    "- offset skips the first N result entries before head_limit is applied"
)
