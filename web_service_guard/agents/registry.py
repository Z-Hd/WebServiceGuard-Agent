from dataclasses import dataclass, field
from typing import Dict

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
        system_prompt=(
            "你是 Bug 探索专家。你的任务是根据用户给定的 Traceback 或报错信息，"
            "通过阅读相关代码，找出导致报错的具体文件、行数和逻辑漏洞。\n"
            "注意：你处于只读沙箱中，如果找不到请直说，不要尝试修改任何代码。"
        ),
        tools=["read", "grep", "glob"],
        permission_mode="plan",
        read_only=True,
    ),
    
    "plan": AgentDefinition(
        agent_type="plan",
        description="根据探查到的代码根因分析，生成详细的代码修改计划（Step-by-Step）。不修改代码。",
        system_prompt=(
            "你是顶级系统架构师。结合探索员之前收集到的线索和根因，"
            "规划出精准的、最简化的代码修改方案。请以清晰清晰的步骤输出修改计划指令。"
        ),
        tools=["read", "grep", "glob"],
        permission_mode="plan",
        read_only=True,
    ),
    
    "execute": AgentDefinition(
        agent_type="execute",
        description="执行修复者。严格根据修改计划操作修复特定的代码文件。",
        system_prompt=(
            "你是一个极为精准的代码修改机器。\n"
            "接收到由上级架构师下发的修改计划后，直接使用工具予以落地实施。\n"
            "禁止无理由的代码大重构，严格且仅修改计划里涉及的逻辑漏洞点。"
        ),
        tools=["edit", "read"],
        permission_mode="acceptEdits",
        read_only=False,
    ),
    
    "verify": AgentDefinition(
        agent_type="verify",
        description="负责 QA 验证。通过跑测试判断修改是否成功。",
        system_prompt=(
            "你是安全测试门禁 (QA)。在代码被另一名探员修改后，"
            "你必须运行必要的测试脚本并读取其成功/失败日志，根据证据给出通过或失败结论报告。\n"
            "如果在你的验证环节出错，你的结论将被用于继续修正代码。"
        ),
        tools=["read", "grep", "glob", "bash"],
        permission_mode="plan",
        read_only=True,
    ),
}

def get_agent_definition(agent_type: str) -> AgentDefinition:
    """根据 agent_type 从注册表中提取配置定义。"""
    if agent_type not in BUILTIN_AGENTS:
        raise ValueError(f"注册表中未发现子 Agent: `{agent_type}`")
    return BUILTIN_AGENTS[agent_type]
