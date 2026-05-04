"""Tool resolution helpers for building per-agent tool pools."""

from __future__ import annotations

from dataclasses import dataclass

from agents.registry import AgentDefinition
from runtime.permission_semantics import (
    PermissionSemanticError,
    normalize_permission_mode,
    resolve_read_only_flag,
)
from tools.base import BaseTool, ToolRegistry


WRITE_TOOL_NAMES = {
    "edit_code",
    "edit",
    "git_commit",
    "feishu_notify",
    "agent",
}


class ToolResolutionError(ValueError):
    """Raised when an agent definition cannot be resolved into a valid tool pool."""


@dataclass(slots=True)
class ResolvedAgentTools:
    """Resolved tool pool and derived execution hints for a sub-agent."""

    tools: list[BaseTool]
    tool_names: list[str]
    invalid_tools: list[str]
    read_only: bool
    permission_mode: str | None


def resolve_agent_tools(
    definition: AgentDefinition,
    tool_registry: ToolRegistry,
) -> ResolvedAgentTools:
    """Resolve an agent definition into a concrete tool pool."""

    available_tools = {tool.name: tool for tool in tool_registry.list_tools()}
    available_names = set(available_tools)
    requested_names = definition.tools

    if requested_names is None:
        resolved_names = list(available_tools)
        invalid_tools: list[str] = []
    else:
        invalid_tools = [name for name in requested_names if name not in available_names]
        if invalid_tools:
            raise ToolResolutionError(
                f"Agent '{definition.agent_type}' references unknown tools: {', '.join(invalid_tools)}"
            )
        resolved_names = list(requested_names)

    denylist = set(definition.disallowed_tools)
    invalid_denied = [name for name in definition.disallowed_tools if name not in available_names]
    if invalid_denied:
        raise ToolResolutionError(
            f"Agent '{definition.agent_type}' disallows unknown tools: {', '.join(invalid_denied)}"
        )

    final_names = [name for name in resolved_names if name not in denylist]
    if not final_names:
        raise ToolResolutionError(
            f"Agent '{definition.agent_type}' resolved to an empty tool set."
        )

    final_tools = [available_tools[name] for name in final_names]
    has_write_tools = any(name in WRITE_TOOL_NAMES for name in final_names)
    try:
        permission_mode = normalize_permission_mode(definition.permission_mode)
        read_only = resolve_read_only_flag(
            agent_type=definition.agent_type,
            permission_mode=permission_mode,
            declared_read_only=definition.read_only,
            has_write_tools=has_write_tools,
        )
    except PermissionSemanticError as exc:
        raise ToolResolutionError(str(exc)) from exc

    return ResolvedAgentTools(
        tools=final_tools,
        tool_names=final_names,
        invalid_tools=[],
        read_only=read_only,
        permission_mode=permission_mode,
    )
