"""Structured Feishu webhook client used by the third-stage delivery flow."""

from __future__ import annotations

from typing import Any

import requests

from web_service_guard.config import config


class FeishuClient:
    """Send delivery notifications through a Feishu incoming webhook."""

    def __init__(
        self,
        *,
        webhook_url: str | None = None,
        session: requests.Session | None = None,
        timeout_sec: int = 15,
    ) -> None:
        self._webhook_url = webhook_url if webhook_url is not None else config.feishu_webhook_url
        self._session = session or requests.Session()
        self._timeout_sec = timeout_sec

    def send_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._webhook_url:
            return {
                "sent": False,
                "error": "Missing Feishu webhook URL.",
            }

        response = self._session.post(
            self._webhook_url,
            json=payload,
            timeout=self._timeout_sec,
        )
        if response.status_code >= 400:
            return {
                "sent": False,
                "status_code": response.status_code,
                "error": response.text.strip() or "Feishu webhook request failed.",
            }

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw": response.text}

        success = bool(response_payload.get("StatusCode") in {0, None} and response_payload.get("code") in {0, None})
        if not success:
            message = response_payload.get("StatusMessage") or response_payload.get("msg") or "Feishu webhook request failed."
            return {
                "sent": False,
                "status_code": response.status_code,
                "error": str(message),
                "raw": response_payload,
            }

        return {
            "sent": True,
            "status_code": response.status_code,
            "raw": response_payload,
        }
