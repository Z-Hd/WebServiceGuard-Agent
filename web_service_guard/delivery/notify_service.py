"""Notification helpers for the third-stage delivery flow."""

from __future__ import annotations

from typing import Any

from web_service_guard.integrations.feishu_client import FeishuClient


class NotifyService:
    """Build and send a compact Feishu notification for a published repair."""

    def __init__(self, *, feishu_client: FeishuClient | None = None) -> None:
        self._feishu_client = feishu_client or FeishuClient()

    def send_notification(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        pr_result: dict[str, Any],
        notification_text: str | None = None,
    ) -> dict[str, Any]:
        payload = self.build_payload(
            prepared_task=prepared_task,
            repair_result=repair_result,
            pr_result=pr_result,
            notification_text=notification_text,
        )
        response = self._feishu_client.send_webhook(payload)
        response.update(
            {
                "channel": "feishu",
                "payload": payload,
            }
        )
        return response

    def build_payload(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        pr_result: dict[str, Any],
        notification_text: str | None = None,
    ) -> dict[str, Any]:
        bug_event = _extract_bug_event(prepared_task)
        artifacts = repair_result.get("artifacts", {})
        plan_output = ((artifacts.get("plan") or {}).get("output") or {})
        verify_output = ((artifacts.get("verify") or {}).get("output") or {})
        verification = verify_output.get("verification_result") or {}
        root_cause = ((plan_output.get("root_cause_analysis") or {}).get("root_cause") or "Unknown")
        verdict = verification.get("verdict") or "UNKNOWN"
        pr_url = pr_result.get("url") or "(PR URL unavailable)"

        markdown = notification_text or (
            f"**Auto-fix ready for review**\n"
            f"- Service: {bug_event.get('service', 'unknown')}\n"
            f"- Summary: {bug_event.get('error_summary', 'unknown incident')}\n"
            f"- Root Cause: {root_cause}\n"
            f"- Verification: {verdict}\n"
            f"- Run ID: {repair_result.get('run_id', '')}\n"
            f"- PR: {pr_url}"
        )
        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "Web Service Guard 自动修复通知",
                        "content": [[{"tag": "text", "text": markdown}]],
                    }
                }
            },
        }


def _extract_bug_event(prepared_task: Any) -> dict[str, Any]:
    repair_task = getattr(prepared_task, "repair_task", None)
    if repair_task is not None:
        bug_event = getattr(repair_task, "bug_event", None)
        if hasattr(bug_event, "to_dict"):
            return bug_event.to_dict()
    if isinstance(prepared_task, dict):
        return dict((prepared_task.get("repair_task") or {}).get("bug_event") or {})
    return {}
