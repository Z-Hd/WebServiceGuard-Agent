"""Minimal OpenAI-compatible LLM adapter for orchestrator/sub-agent smoke tests."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from schemas.agent_messages import AgentTurn, ToolCall
from tools.base import BaseTool


DEFAULT_BASE_URL = "https://api.asxs.top/v1"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_TIMEOUT_SEC = 180


@dataclass(slots=True)
class OpenAICompatibleLLMAdapter:
    """Minimal chat-completions adapter that returns AgentTurn objects."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_sec: int = DEFAULT_TIMEOUT_SEC

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLMAdapter":
        api_key = os.environ.get("CCH_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("CCH_API_KEY or OPENAI_API_KEY is required")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
            model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
            timeout_sec=int(os.environ.get("OPENAI_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC))),
        )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[BaseTool],
        system_prompt: str,
        tool_use_context: Any | None = None,
    ) -> AgentTurn:
        payload = {
            "model": self.model,
            "messages": self._build_messages(system_prompt, messages),
            "tools": self._build_tools(tools),
            "tool_choice": "auto" if tools else "none",
            "temperature": 0,
        }
        response = requests.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        raw = response.json()
        choice = raw["choices"][0]["message"]
        tool_calls = choice.get("tool_calls") or []
        content = self._message_content_to_text(choice.get("content"))
        if tool_calls:
            call = tool_calls[0]
            args_raw = call["function"].get("arguments") or "{}"
            try:
                arguments = json.loads(args_raw)
            except json.JSONDecodeError:
                arguments = {"_raw_arguments": args_raw}
            return AgentTurn(
                kind="tool",
                content=content or f"Calling tool {call['function']['name']}",
                tool_call=ToolCall(
                    name=call["function"]["name"],
                    arguments=arguments,
                ),
                raw=raw,
            )
        return AgentTurn(
            kind="final",
            content=content or "",
            raw=raw,
        )

    def _build_messages(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        converted: list[dict[str, str]] = []
        if messages and messages[0].get("role") == "system":
            first_content = self._message_content_to_text(messages[0].get("content"))
            converted.append({"role": "system", "content": first_content})
            iterable = messages[1:]
        else:
            converted.append({"role": "system", "content": system_prompt})
            iterable = messages
        for message in iterable:
            role = message.get("role", "user")
            content = self._message_content_to_text(message.get("content"))
            if role == "tool":
                tool_name = message.get("name", "tool")
                converted.append(
                    {
                        "role": "user",
                        "content": f"Tool result from {tool_name}:\n{content}",
                    }
                )
            elif role in {"user", "assistant"}:
                converted.append({"role": role, "content": content})
            elif role == "system":
                converted.append({"role": "user", "content": content})
            else:
                converted.append({"role": "user", "content": content})
        return converted

    def _build_tools(self, tools: list[BaseTool]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def _message_content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)
