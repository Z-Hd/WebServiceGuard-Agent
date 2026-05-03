"""Prompt and descriptive constants for FileReadTool."""

FILE_READ_TOOL_NAME = "read"
DESCRIPTION = "Read a text file from the local filesystem."

USAGE_NOTES = (
    "Usage:\n"
    "- file_path must be an absolute path\n"
    "- offset is 1-based and defaults to 1\n"
    "- limit defaults to 200 lines and is capped at 2000 lines\n"
    "- this tool only supports text files, not directories or binary files"
)
