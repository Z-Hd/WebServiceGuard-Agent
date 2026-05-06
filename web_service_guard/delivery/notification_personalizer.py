"""Single-shot LLM notification personalization for the third-stage delivery flow."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from web_service_guard.config import config


DEFAULT_BASE_URL = "https://api.asxs.top/v1"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_TIMEOUT_SEC = 60


@dataclass(slots=True)
class NotificationPersonalizationResult:
    """Outcome of optional notification personalization."""

    success: bool
    text: str | None
    llm_used: bool
    fallback_reason: str | None = None
    profile_id: str | None = None
    profile_source: str | None = None
    prompt_version: str = "v1"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "llm_used": self.llm_used,
            "fallback_reason": self.fallback_reason,
            "profile_id": self.profile_id,
            "profile_source": self.profile_source,
            "prompt_version": self.prompt_version,
            "error": self.error,
        }


class NotificationPersonalizer:
    """Generate a personalized developer notification from structured repair facts."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        # Importing config above ensures the repository-local .env is loaded first.
        _ = config.dotenv_path
        self._api_key = api_key if api_key is not None else self._resolve_api_key()
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        self._model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        self._timeout_sec = timeout_sec

    def personalize(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        pr_result: dict[str, Any],
        profile_resolution: Any,
    ) -> NotificationPersonalizationResult:
        profile = dict(getattr(profile_resolution, "profile", {}) or {})
        profile_id = str(profile.get("id", "")).strip() or None
        profile_source = getattr(profile_resolution, "source_path", None)

        if not self._api_key:
            return NotificationPersonalizationResult(
                success=False,
                text=None,
                llm_used=False,
                fallback_reason="missing_api_key",
                profile_id=profile_id,
                profile_source=profile_source,
                error="Missing OPENAI_API_KEY or CCH_API_KEY for notification personalization.",
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            prepared_task=prepared_task,
            repair_result=repair_result,
            pr_result=pr_result,
            profile=profile,
        )
        try:
            text = self._complete(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            return NotificationPersonalizationResult(
                success=False,
                text=None,
                llm_used=True,
                fallback_reason="llm_generation_failed",
                profile_id=profile_id,
                profile_source=profile_source,
                error=str(exc),
            )

        cleaned = text.strip()
        if not cleaned:
            return NotificationPersonalizationResult(
                success=False,
                text=None,
                llm_used=True,
                fallback_reason="empty_llm_response",
                profile_id=profile_id,
                profile_source=profile_source,
                error="LLM returned an empty notification.",
            )

        return NotificationPersonalizationResult(
            success=True,
            text=cleaned,
            llm_used=True,
            profile_id=profile_id,
            profile_source=profile_source,
        )

    def _build_system_prompt(self) -> str:
        return (
            "You write concise personalized developer notifications for automated bug-fix delivery.\n"
            "Only reorganize and phrase the provided facts; do not invent new facts.\n"
            "Do not change the bug status, verification verdict, PR URL, or modified files.\n"
            "If information is missing, omit it instead of guessing.\n"
            "Write like a teammate speaking directly to the target developer, not like a broadcast announcement.\n"
            "Follow the requested section order strictly when it is provided.\n"
            "Make the conclusion and action item visually distinct.\n"
            "Return only the final notification text in Markdown.\n"
        )

    def _build_user_prompt(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        pr_result: dict[str, Any],
        profile: dict[str, Any],
    ) -> str:
        bug_event = _extract_bug_event(prepared_task)
        artifacts = repair_result.get("artifacts", {})
        plan_output = ((artifacts.get("plan") or {}).get("output") or {})
        execute_output = ((artifacts.get("execute") or {}).get("output") or {})
        verify_output = ((artifacts.get("verify") or {}).get("output") or {})
        verification = verify_output.get("verification_result") or {}
        root_cause = ((plan_output.get("root_cause_analysis") or {}).get("root_cause") or "Unknown")
        files_to_modify = (plan_output.get("repair_plan") or {}).get("files_to_modify") or []
        modified_files = (execute_output.get("patch_result") or {}).get("modified_files") or []
        successful_checks = verification.get("successful_checks") or []
        failed_tests = verification.get("failed_tests") or []
        action_required = "Please review and merge the PR if it looks good."
        display_name = str(profile.get("display_name", "")).strip()
        preferred_sections = profile.get("preferred_sections") or []
        opening_style = str(profile.get("opening_style", "neutral")).strip() or "neutral"
        emoji_level = str(profile.get("emoji_level", "low")).strip() or "low"
        action_style = str(profile.get("action_style", "explicit")).strip() or "explicit"

        profile_payload = {
            "id": profile.get("id"),
            "display_name": display_name or None,
            "language": profile.get("language", "zh-CN"),
            "tone": profile.get("tone", "concise"),
            "verbosity": profile.get("verbosity", "short"),
            "opening_style": opening_style,
            "emoji_level": emoji_level,
            "action_style": action_style,
            "format_preferences": profile.get("format_preferences") or [],
            "preferred_sections": preferred_sections,
            "avoid": profile.get("avoid") or [],
            "notes": profile.get("notes") or "",
        }
        facts_payload = {
            "service": bug_event.get("service"),
            "summary": bug_event.get("error_summary"),
            "root_cause": root_cause,
            "files_to_modify": files_to_modify,
            "modified_files": modified_files,
            "verification_verdict": verification.get("verdict"),
            "ready_for_pr": verification.get("ready_for_pr"),
            "successful_checks": successful_checks,
            "failed_tests": failed_tests,
            "pr_url": pr_result.get("url"),
            "run_id": repair_result.get("run_id"),
            "action_required": action_required,
        }
        return (
            "Developer profile:\n"
            f"{json.dumps(profile_payload, ensure_ascii=False, indent=2)}\n\n"
            "Repair facts:\n"
            f"{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
            "Write a Feishu-ready Markdown notification addressed to the target developer.\n"
            "Requirements:\n"
            "- Keep the message under 10 lines.\n"
            "- If display_name is available, address the developer directly by name.\n"
            "- Use the preferred section order when provided.\n"
            "- Distinguish conclusion and next action clearly.\n"
            "- Mention the PR link.\n"
            "- Make the current action required clear.\n"
            "- Prefer concise phrasing.\n"
            "- Do not add any facts beyond the repair facts above.\n"
            "- Use Markdown bullets or short labeled lines; avoid long paragraphs.\n"
            "- Keep the tone aligned with the developer profile.\n"
            "\nPreferred output guidance:\n"
            "- `greeting`: a short direct greeting to the developer.\n"
            "- `conclusion`: the repair outcome in one short line.\n"
            "- `root-cause`: why the bug happened.\n"
            "- `files-changed`: which files were modified.\n"
            "- `verification`: the verification result.\n"
            "- `action-item`: what the developer should do next.\n"
            "- `pr-link`: the PR link.\n"
        )

    def _complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [],
            "tool_choice": "none",
            "temperature": 0,
        }
        response = requests.post(
            f"{self._base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout_sec,
        )
        response.raise_for_status()
        raw = response.json()
        choice = raw["choices"][0]["message"]
        content = choice.get("content")
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False)

    def _resolve_api_key(self) -> str | None:
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if openai_api_key:
            return openai_api_key
        cch_api_key = os.environ.get("CCH_API_KEY")
        return cch_api_key if cch_api_key else None


def _extract_bug_event(prepared_task: Any) -> dict[str, Any]:
    repair_task = getattr(prepared_task, "repair_task", None)
    if repair_task is not None:
        bug_event = getattr(repair_task, "bug_event", None)
        if bug_event is not None and hasattr(bug_event, "to_dict"):
            return bug_event.to_dict()
    if isinstance(prepared_task, dict):
        return dict((prepared_task.get("repair_task") or {}).get("bug_event") or {})
    return {}
