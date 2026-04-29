import os
import shutil
import difflib
from web_service_guard.primitive_tools.base import PrimitiveTool
from web_service_guard.enums import ToolStatus
from web_service_guard.config import config

class EditCode(PrimitiveTool):
    """修改代码工具"""
    
    def __init__(self):
        self.backup_enabled = config.get('code_modifier_backup_enabled', True)
        self.backup_dir = config.get('code_modifier_backup_dir', './backups')
        
        # 创建备份目录
        if self.backup_enabled and not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def execute(self, run_id: str, iteration: int, input_data: dict, constraints: dict) -> dict:
        """执行代码修改"""
        try:
            file = input_data.get('file')
            edit_type = input_data.get("edit_type", "replace_content")
            patch = input_data.get("patch")
            changes = input_data.get("changes", patch)
            invoked_by = constraints.get("invoked_by")
            
            if not file or not changes:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="缺少文件路径或修改内容",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_EDIT_CODE_FAILED", "message": "缺少文件路径或修改内容", "retryable": False, "source": "EditCode"}],
                    input_data=input_data,
                    invoked_by=invoked_by,
                )
            
            if not os.path.exists(file):
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="代码文件不存在",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_EDIT_CODE_FAILED", "message": "代码文件不存在", "retryable": False, "source": "EditCode"}],
                    input_data=input_data,
                    invoked_by=invoked_by,
                )
            
            # 备份原文件
            if self.backup_enabled:
                backup_file = os.path.join(self.backup_dir, os.path.basename(file) + f'.bak_{run_id}')
                shutil.copy2(file, backup_file)
            
            # 读取原文件
            with open(file, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # 应用修改
            modified_code = code
            if edit_type == "replace_content" and isinstance(changes, str):
                modified_code = changes
            elif isinstance(changes, dict) and 'old_code' in changes and 'new_code' in changes:
                modified_code = modified_code.replace(changes['old_code'], changes['new_code'])
            else:
                return self._create_result(
                    run_id=run_id,
                    iteration=iteration,
                    status=ToolStatus.FAILED,
                    summary="不支持的修改类型",
                    output={},
                    artifacts=[],
                    errors=[{"code": "TOOL_EDIT_CODE_FAILED", "message": "不支持的修改类型", "retryable": False, "source": "EditCode"}],
                    input_data=input_data,
                    invoked_by=invoked_by,
                )
            
            # 保存修改后的文件
            with open(file, 'w', encoding='utf-8') as f:
                f.write(modified_code)
            
            # 生成diff摘要
            diff = difflib.unified_diff(
                code.splitlines(keepends=True),
                modified_code.splitlines(keepends=True),
                fromfile=file,
                tofile=file
            )
            diff_summary = list(diff)
            lines_added = sum(1 for line in diff_summary if line.startswith('+') and not line.startswith('+++'))
            lines_removed = sum(1 for line in diff_summary if line.startswith('-') and not line.startswith('---'))
            
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.SUCCESS,
                summary=f"成功修改代码文件 {file}",
                output={
                    "file": file,
                    "modified": True,
                    "modified_file": file,
                    "diff_summary": diff_summary,
                    "lines_added": lines_added,
                    "lines_removed": lines_removed,
                },
                artifacts=[file],
                errors=[],
                input_data=input_data,
                invoked_by=invoked_by,
            )
        except Exception as e:
            return self._create_result(
                run_id=run_id,
                iteration=iteration,
                status=ToolStatus.FAILED,
                summary="修改代码失败",
                output={},
                artifacts=[],
                errors=[{"code": "TOOL_EDIT_CODE_FAILED", "message": str(e), "retryable": True, "source": "EditCode"}],
                input_data=input_data,
                invoked_by=constraints.get("invoked_by"),
            )
