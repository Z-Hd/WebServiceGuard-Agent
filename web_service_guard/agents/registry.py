from dataclasses import dataclass, field
from typing import Dict

from prompts.subagents import (
    build_execute_system_prompt,
    build_explore_system_prompt,
    build_plan_system_prompt,
    build_verify_system_prompt,
)

@dataclass
class AgentDefinition:
    """
    定义一个 Agent 的配置信息（不包含任何运行逻辑）。
    它将用来向系统描述这个被召唤出来的实体：叫什么、做什么的、拥有什么个性、手里有什么工具限制。
    """
    agent_type: str
    description: str
    system_prompt: str
    tools: list[str] | None = None
    disallowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    max_turns: int | None = None
    permission_mode: str | None = None
    read_only: bool | None = None

# 内置的基础 Agent 兵种配置大表
BUILTIN_AGENTS: Dict[str, AgentDefinition] = {
    "explore": AgentDefinition(
        agent_type="explore",
        description="探索并定位 Bug 根因。当你收到一个异常 Traceback 时调用。只读能力。",
        system_prompt=build_explore_system_prompt(),
        tools=["read", "grep", "glob"],
        permission_mode="plan",
        read_only=True,
    ),
    
    "plan": AgentDefinition(
        agent_type="plan",
        description="根据探查到的代码根因分析，生成详细的代码修改计划（Step-by-Step）。不修改代码。",
        system_prompt=build_plan_system_prompt(),
        tools=["read", "grep", "glob"],
        permission_mode="plan",
        read_only=True,
    ),
    
    "execute": AgentDefinition(
        agent_type="execute",
        description="执行修复者。严格根据修改计划操作修复特定的代码文件。",
        system_prompt=build_execute_system_prompt(),
        tools=["edit", "read"],
        permission_mode="acceptEdits",
        read_only=False,
    ),
    
    "verify": AgentDefinition(
        agent_type="verify",
        description="负责 QA 验证。通过跑测试判断修改是否成功。",
        system_prompt=build_verify_system_prompt(),
        tools=["read", "grep", "glob", "bash"],
        max_turns=10,
        permission_mode="plan",
        read_only=True,
    ),
}

def get_agent_definition(agent_type: str) -> AgentDefinition:
    """根据 agent_type 从注册表中提取配置定义。"""
    if agent_type not in BUILTIN_AGENTS:
        raise ValueError(f"注册表中未发现子 Agent: `{agent_type}`")
    return BUILTIN_AGENTS[agent_type]
