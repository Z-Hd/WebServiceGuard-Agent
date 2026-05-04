"""PR construction and publication helpers for the third-stage delivery flow."""

from __future__ import annotations

from typing import Any

from web_service_guard.integrations.github_client import GitHubClient


class PRService:
    """Build a PR title/body from structured repair artifacts and publish it."""

    def __init__(self, *, github_client: GitHubClient | None = None) -> None:
        self._github_client = github_client or GitHubClient()

    def create_pr(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
        publish_result: dict[str, Any],
    ) -> dict[str, Any]:
        bug_event = _extract_bug_event(prepared_task)
        repo_full_name = _normalize_repo_full_name(str(bug_event.get("repo", "")).strip())
        if not repo_full_name:
            return {
                "created": False,
                "error": "Could not derive a GitHub repository name from the repair task.",
            }

        title = self.build_title(bug_event)
        body = self.build_body(
            bug_event=bug_event,
            repair_result=repair_result,
            publish_result=publish_result,
        )
        branch_name = str(publish_result.get("branch_name", "")).strip()
        base_branch = str(bug_event.get("branch", "")).strip()
        if not branch_name or not base_branch:
            return {
                "created": False,
                "error": "Missing branch information required to create the PR.",
            }

        response = self._github_client.create_pull_request(
            repo_full_name=repo_full_name,
            title=title,
            body=body,
            head=branch_name,
            base=base_branch,
        )
        response.update(
            {
                "title": title,
                "body": body,
                "repo_full_name": repo_full_name,
                "head": branch_name,
                "base": base_branch,
            }
        )
        return response

    def build_title(self, bug_event: dict[str, Any]) -> str:
        service = str(bug_event.get("service", "")).strip() or "service"
        error_type = str(bug_event.get("error_type", "")).strip()
        if error_type:
            return f"Auto-fix: {service} - {error_type}"
        summary = str(bug_event.get("error_summary", "")).strip() or "unknown failure"
        return f"Auto-fix: {service} - {summary[:72]}"

    def build_body(
        self,
        *,
        bug_event: dict[str, Any],
        repair_result: dict[str, Any],
        publish_result: dict[str, Any],
    ) -> str:
        artifacts = repair_result.get("artifacts", {})
        plan_output = ((artifacts.get("plan") or {}).get("output") or {})
        execute_output = ((artifacts.get("execute") or {}).get("output") or {})
        verify_output = ((artifacts.get("verify") or {}).get("output") or {})

        root_cause = ((plan_output.get("root_cause_analysis") or {}).get("root_cause") or "Unknown")
        evidence = (plan_output.get("root_cause_analysis") or {}).get("evidence") or []
        fix_plan = (plan_output.get("repair_plan") or {}).get("fix_plan") or []
        modified_files = (execute_output.get("patch_result") or {}).get("modified_files") or []
        verification = verify_output.get("verification_result") or {}
        verdict = verification.get("verdict") or "UNKNOWN"
        failed_tests = verification.get("failed_tests") or []
        successful_checks = verification.get("successful_checks") or []
        diff_stat = str(publish_result.get("diff_stat", "")).strip()

        sections = [
            "## Incident Summary",
            str(bug_event.get("error_summary", "")).strip() or "Unknown incident",
            "",
            "## Root Cause",
            root_cause,
            "",
            "## Evidence",
            _render_list(evidence) or "- No structured evidence captured",
            "",
            "## Repair Plan",
            _render_list(fix_plan) or "- No repair steps captured",
            "",
            "## Files Changed",
            _render_list(modified_files) or "- No modified files recorded",
            "",
            "## Verification Result",
            f"- Verdict: {verdict}",
            f"- Ready for PR: {bool(verification.get('ready_for_pr'))}",
            f"- Successful checks: {', '.join(successful_checks) if successful_checks else 'none recorded'}",
            f"- Failed tests: {', '.join(failed_tests) if failed_tests else 'none'}",
        ]
        if diff_stat:
            sections.extend(["", "## Git Diff Stat", "```text", diff_stat, "```"])
        sections.extend(["", "## Run Metadata", f"- Run ID: {repair_result.get('run_id', '')}"])
        return "\n".join(sections).strip()


def _render_list(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items if str(item).strip())


def _extract_bug_event(prepared_task: Any) -> dict[str, Any]:
    repair_task = getattr(prepared_task, "repair_task", None)
    if repair_task is not None:
        bug_event = getattr(repair_task, "bug_event", None)
        if hasattr(bug_event, "to_dict"):
            return bug_event.to_dict()
    if isinstance(prepared_task, dict):
        return dict((prepared_task.get("repair_task") or {}).get("bug_event") or {})
    return {}


def _normalize_repo_full_name(repo_value: str) -> str:
    value = repo_value.strip().rstrip("/")
    if not value:
        return ""
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("git@github.com:"):
        return value.removeprefix("git@github.com:")
    if value.startswith("https://github.com/"):
        return value.removeprefix("https://github.com/")
    if value.startswith("http://github.com/"):
        return value.removeprefix("http://github.com/")
    if value.count("/") == 1 and "://" not in value and "@" not in value:
        return value
    return ""
