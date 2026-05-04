"""Structured GitHub API client used by the third-stage delivery flow."""

from __future__ import annotations

from typing import Any

import requests

from web_service_guard.config import config


class GitHubClient:
    """Small wrapper around the GitHub pull-request creation API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        session: requests.Session | None = None,
        timeout_sec: int = 20,
    ) -> None:
        self._token = token if token is not None else config.github_token
        self._api_url = (api_url or config.github_api_url).rstrip("/")
        self._session = session or requests.Session()
        self._timeout_sec = timeout_sec

    def create_pull_request(
        self,
        *,
        repo_full_name: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        if not self._token:
            return {
                "created": False,
                "error": "Missing GitHub token.",
            }

        response = self._session.post(
            f"{self._api_url}/repos/{repo_full_name}/pulls",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
            timeout=self._timeout_sec,
        )
        if response.status_code >= 400:
            return {
                "created": False,
                "error": _extract_error_message(response),
                "status_code": response.status_code,
            }

        payload = response.json()
        return {
            "created": True,
            "url": payload.get("html_url"),
            "number": payload.get("number"),
            "raw": payload,
        }


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"GitHub API request failed with status {response.status_code}."

    if isinstance(payload, dict):
        message = payload.get("message")
        errors = payload.get("errors")
        if message and errors:
            return f"{message}: {errors}"
        if message:
            return str(message)
    return response.text.strip() or f"GitHub API request failed with status {response.status_code}."
