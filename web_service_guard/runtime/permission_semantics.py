"""Minimal permission-mode semantics for sub-agent execution."""

from __future__ import annotations


SUPPORTED_PERMISSION_MODES = frozenset(
    {
        "default",
        "plan",
        "acceptEdits",
        "bypassPermissions",
    }
)


class PermissionSemanticError(ValueError):
    """Raised when an agent definition violates permission-mode semantics."""


def normalize_permission_mode(permission_mode: str | None) -> str:
    """Normalize an optional permission mode into a supported concrete value."""

    if permission_mode is None:
        return "default"
    if permission_mode not in SUPPORTED_PERMISSION_MODES:
        supported = ", ".join(sorted(SUPPORTED_PERMISSION_MODES))
        raise PermissionSemanticError(
            f"Unsupported permission_mode '{permission_mode}'. Supported modes: {supported}"
        )
    return permission_mode


def resolve_read_only_flag(
    *,
    agent_type: str,
    permission_mode: str,
    declared_read_only: bool | None,
    has_write_tools: bool,
) -> bool:
    """Resolve the effective read-only flag and validate semantic conflicts."""

    if declared_read_only is True and has_write_tools:
        raise PermissionSemanticError(
            f"Agent '{agent_type}' declares read_only=True but still exposes write-capable tools."
        )

    if declared_read_only is False and not has_write_tools:
        raise PermissionSemanticError(
            f"Agent '{agent_type}' declares read_only=False but has no write-capable tools."
        )

    if permission_mode == "plan":
        if has_write_tools:
            raise PermissionSemanticError(
                f"Agent '{agent_type}' uses permission_mode='plan' but still exposes write-capable tools."
            )
        if declared_read_only is False:
            raise PermissionSemanticError(
                f"Agent '{agent_type}' uses permission_mode='plan' and cannot declare read_only=False."
            )
        return True

    if declared_read_only is not None:
        return declared_read_only
    return not has_write_tools
