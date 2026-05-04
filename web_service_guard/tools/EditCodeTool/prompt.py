"""Prompt and descriptive constants for EditCodeTool."""

from tools.FileReadTool.prompt import FILE_READ_TOOL_NAME

EDIT_CODE_TOOL_NAME = "edit"
DESCRIPTION = "Apply exact string replacements to an existing text file."

USAGE_NOTES = (
    "Performs exact string replacements in files.\n\n"
    "Usage:\n"
    f"- You must use `{FILE_READ_TOOL_NAME}` at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file first\n"
    "- file_path must be an absolute path\n"
    "- the target file must already exist and must be a text file\n"
    "- old_string must match the current file content exactly\n"
    "- always prefer editing existing files over creating new files\n"
    "- the edit will fail if old_string is not unique in the file when replace_all is false\n"
    "- use the smallest old_string that is clearly unique; usually a few adjacent lines are enough, and very large context blocks should be avoided unless necessary\n"
    "- if old_string is not unique, either provide a more specific old_string with nearby context or use replace_all to change every matching instance\n"
    "- use replace_all=true for replacing or renaming every occurrence of the same text in the file\n"
    "- do not use this tool for broad refactors when a smaller, exact replacement can solve the problem"
)
