"""Prompt and descriptive constants for EditCodeTool."""

EDIT_CODE_TOOL_NAME = "edit"
DESCRIPTION = "Apply exact string replacements to an existing text file."

USAGE_NOTES = (
    "Usage:\n"
    "- file_path must be an absolute path\n"
    "- the target file must already exist and must be a text file\n"
    "- you must read the file before editing it\n"
    "- old_string must match the current file content exactly\n"
    "- when replace_all is false, old_string must be unique in the file\n"
    "- set replace_all=true only when all matching instances should be replaced"
)
