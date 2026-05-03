"""Base protocol and shared structures for all Tool implementations."""
from typing import Any, Dict, List, Optional

class BaseTool:
    """
    所有 Tool(包括原子工具和代理工具) 的基类接口。
    所有的工具应当子类化此接口并实现 name, description, input_schema 和 execute 方法。
    """
    name: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = {}

    def execute(self, **kwargs) -> str:
        """
        工具的核心执行逻辑。
        应当返回描述执行操作的结果文本或报错信息供 LLM 阅读。
        """
        raise NotImplementedError("Subclasses must implement the execute method")

    def execute_structured(self, **kwargs) -> dict[str, Any]:
        """
        可选的结构化执行接口。
        默认未实现，由支持结构化输出的工具自行覆盖。
        """
        raise NotImplementedError("Structured execution is not implemented for this tool")

    def format_structured_result(self, result: dict[str, Any]) -> str:
        """
        将结构化结果转成提供给 LLM 的文本。
        默认实现仅返回 summary，并在失败时加 ERROR 前缀。
        """
        summary = str(result.get("summary", ""))
        if result.get("status") == "failed":
            return f"ERROR: {summary}" if summary else "ERROR"
        return summary


class ToolRegistry:
    """
    工具注册表，管理和检索所有的可用工具。
    在启动子Agent或主Agent时，通过此注册列表检索出指定名称的工具集组成专用的 Tool Pool。
    """
    def __init__(self):
        self._tools: Dict[str, 'BaseTool'] = {}

    def register(self, tool_instance: BaseTool):
        if not tool_instance.name:
            raise ValueError(f"Tool {tool_instance.__class__.__name__} is missing a 'name'.")
        self._tools[tool_instance.name] = tool_instance

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def get_tools_by_names(self, names: List[str]) -> List[BaseTool]:
        found_tools = []
        import logging
        for name in names:
            if name in self._tools:
                found_tools.append(self._tools[name])
            else:
                logging.getLogger(__name__).warning(f"Tool Registry 尚未寻找到名称为 '{name}' 的工具。已被略过。")
        return found_tools

# 全局工具池单例
global_tool_registry = ToolRegistry()
