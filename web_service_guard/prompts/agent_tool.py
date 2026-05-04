"""Tool description builder for the second-stage agent dispatcher."""

from __future__ import annotations

from typing import Iterable

from agents.registry import AgentDefinition


def _format_agent_line(agent: AgentDefinition) -> str:
    tools = ", ".join(agent.tools or [])
    return f"- {agent.agent_type}: {agent.description} (Tools: {tools})"


def build_agent_tool_description(agent_definitions: Iterable[AgentDefinition]) -> str:
    agent_lines = "\n".join(_format_agent_line(agent) for agent in agent_definitions)

    return (
        "Launch a new agent to handle one focused part of the second-stage repair workflow autonomously.\n\n"
        "The `agent` tool is the only tool the main Repair Orchestrator should call directly. "
        "Sub-agents handle the actual code exploration, planning, execution, and verification work.\n\n"
        "Available agent types and the tools they have access to:\n"
        f"{agent_lines}\n\n"
        "When using the `agent` tool, specify an `agent_type` to select which specialized agent to use. "
        "Each invocation starts fresh, so provide a complete task description in `user_prompt`.\n\n"
        "When NOT to use the `agent` tool:\n"
        "- If the next step is already obvious from prior structured evidence, do not spawn `explore` again just to reread the same context.\n"
        "- If you only need to decide whether to continue, retry, or stop based on structured outputs already returned by a prior sub-agent, reason from those outputs instead of launching a new agent immediately.\n"
        "- Do not dispatch `execute` if you still lack enough grounded context to make a safe code change.\n"
        "- Do not use `verify` before code has actually been changed.\n"
        "- Do not use a vague agent call when a more specific agent is clearly appropriate.\n\n"
        "## Agent selection guidance\n"
        "- Use `explore` when you need more evidence: traceback analysis, file discovery, code-path tracing, or related test/config lookup.\n"
        "- Use `plan` when you already have evidence and need to synthesize it into a concrete repair strategy or decide between multiple fix directions.\n"
        "- Use `execute` when the intended change is clear enough to implement safely and the edit scope can be described concretely.\n"
        "- Use `verify` when you need an evidence-backed verdict on whether the current implementation is truly ready for PR.\n"
        "- Choose the next agent based on what information is missing right now, not on a fixed sequence.\n"
        "- Reuse structured outputs from earlier sub-agents when they are sufficient; do not re-run a stage out of habit.\n"
        "- If a sub-agent fails or returns insufficient evidence, either retry with a better brief or stop for human review.\n\n"
        "## Writing the prompt\n"
        "Brief the agent like a smart colleague who just walked into the room — it has not seen this conversation, "
        "doesn't know what you've tried, and doesn't understand why this task matters.\n"
        "- Explain what you are trying to accomplish and why.\n"
        "- Describe what you have already learned or ruled out.\n"
        "- Give enough context that the agent can make judgment calls instead of following a narrow script.\n"
        "- Include concrete file paths, traceback clues, modified files, or success criteria when available.\n"
        "- If you need a short response, say so.\n"
        "- For `verify`, ask for evidence-backed validation rather than a guess.\n\n"
        "Terse command-style prompts produce shallow, generic work.\n\n"
        "Never delegate understanding. Do not write prompts like \"based on your findings, fix the bug\" or "
        "\"based on the research, implement it.\" Those phrases push synthesis onto the sub-agent instead of doing it "
        "yourself. Write prompts that prove you understood the current situation: include the evidence, the scope, "
        "and the decision the sub-agent needs to make.\n\n"
        "## Usage notes\n"
        "- `agent_type` must be one of: `explore`, `plan`, `execute`, `verify`.\n"
        "- `user_prompt` is required and should be task-specific.\n"
        "- `system_prompt_override` is optional and should be used only for controlled prompt experiments.\n"
        "- `max_turns` can cap sub-agent loop length for the current invocation.\n"
        "- The sub-agent's result is returned to the orchestrator as structured output; use that structured output to decide what to do next.\n"
        "- `orchestrator_context` supplements the briefing, but it does not replace the need for a complete `user_prompt`.\n"
        "- The orchestrator should summarize or act on the result, not blindly repeat the sub-agent's final sentence as its own conclusion.\n\n"
        "## Example usage\n"
        "<example>\n"
        "If you have a traceback but no grounded root cause yet, call `explore` with the traceback, repo clues, and the investigation question.\n"
        "Example: `agent_type=\"explore\"`, `user_prompt=\"Investigate this traceback, locate the failing code path, and report the most likely root cause with file evidence.\"`\n"
        "</example>\n\n"
        "<example>\n"
        "If you already have suspect files and evidence but still need a concrete repair strategy, call `plan` with the repair goal rather than asking it to rediscover the bug.\n"
        "Example: `agent_type=\"plan\"`, `user_prompt=\"Using the exploration evidence, produce a minimal repair plan and identify the files that must change.\"`\n"
        "</example>\n\n"
        "<example>\n"
        "If the intended change is clear enough to implement safely, call `execute` with a tightly scoped implementation brief.\n"
        "Example: `agent_type=\"execute\"`, `user_prompt=\"Apply the approved repair plan exactly, keeping the edit scope minimal.\"`\n"
        "</example>\n\n"
        "<example>\n"
        "If code has been changed and you need an acceptance verdict, call `verify` with explicit validation goals.\n"
        "Example: `agent_type=\"verify\"`, `user_prompt=\"Run the necessary checks for the modified files and return a verdict backed by command output.\"`\n"
        "</example>"
    )
