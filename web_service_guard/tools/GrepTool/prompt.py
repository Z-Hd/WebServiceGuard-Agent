"""Prompt and descriptive constants for GrepTool."""

from tools.BashTool.prompt import BASH_TOOL_NAME

GREP_TOOL_NAME = "grep"
DESCRIPTION = "Search text file contents using regular expressions."

USAGE_NOTES = (
    "Usage:\n"
    f"- ALWAYS use `{GREP_TOOL_NAME}` for search tasks. NEVER invoke `grep` or `rg` through `{BASH_TOOL_NAME}` when this tool can do the job\n"
    "- pattern must be a valid regular expression\n"
    "- supports regex searches such as `log.*Error` or `function\\s+\\w+`\n"
    "- path may point to a file or directory; if omitted, current working directory is searched\n"
    "- filter files with `glob`, for example `*.py` or `**/*.md`\n"
    "- output_mode defaults to `files_with_matches`\n"
    "- output_mode=`content` shows matching lines and optional context\n"
    "- output_mode=`files_with_matches` shows only file paths\n"
    "- output_mode=`count` shows match counts\n"
    "- context_lines is only meaningful in `content` mode\n"
    "- head_limit defaults to 50 and may be set to 0 for unlimited results\n"
    "- offset skips the first N result entries before head_limit is applied\n"
    "- use the `agent` tool for open-ended investigations that require multiple rounds of searching and synthesis"
)
