"""Prompt and descriptive constants for FileReadTool."""

from tools.BashTool.prompt import BASH_TOOL_NAME

FILE_READ_TOOL_NAME = "read"
DESCRIPTION = "Read a text file from the local filesystem."
DEFAULT_LINES_TO_READ = 200
MAX_LINES_TO_READ = 2000

OFFSET_INSTRUCTION_DEFAULT = (
    "- You can optionally specify a line offset and limit, but it is often better to read the whole file "
    "by not providing these parameters when the file is reasonably small"
)

OFFSET_INSTRUCTION_TARGETED = (
    "- When you already know which part of the file you need, only read that part"
)

USAGE_NOTES = (
    "Reads a file from the local filesystem. You can access a file directly by using this tool.\n"
    "Assume this tool can read files within the runtime's allowed scope. If the user provides a file path, it is acceptable to try reading it; if it does not exist or cannot be read, an error will be returned.\n\n"
    "Usage:\n"
    "- The file_path parameter must be an absolute path, not a relative path\n"
    f"- By default, it reads up to {DEFAULT_LINES_TO_READ} lines starting from the beginning of the file\n"
    f"{OFFSET_INSTRUCTION_DEFAULT}\n"
    f"{OFFSET_INSTRUCTION_TARGETED}\n"
    "- offset is 1-based and defaults to 1\n"
    f"- limit is capped at {MAX_LINES_TO_READ} lines\n"
    "- This tool only supports text files, not directories or binary files\n"
    f"- This tool can only read files, not directories. To inspect a directory, use a read-only `ls` command via `{BASH_TOOL_NAME}`\n"
    "- If the file exists but is empty, the result may contain an empty content payload rather than visible file text"
)
