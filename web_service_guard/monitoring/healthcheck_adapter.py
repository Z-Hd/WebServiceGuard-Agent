from __future__ import annotations

from datetime import datetime, timezone
from urllib import error, request

from web_service_guard.config import config
from web_service_guard.schemas.incident_trigger import IncidentTrigger


class HealthcheckAdapter:
    """Healthcheck trigger source for the first phase."""

    def __init__(
        self,
        *,
        healthcheck_urls: list[str] | None = None,
        timeout: int | None = None,
    ) -> None:
        self.healthcheck_urls = list(healthcheck_urls or config.get("healthcheck_urls", []))
        self.timeout = timeout or config.get("healthcheck_timeout", 5)

    def check_health(self) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for url in self.healthcheck_urls:
            try:
                with request.urlopen(url, timeout=self.timeout) as response:
                    status_code = int(response.getcode())
                status = "healthy" if status_code == 200 else "unhealthy"
                results.append(
                    {
                        "url": url,
                        "status": status,
                        "status_code": status_code,
                    }
                )
            except error.HTTPError as exc:
                results.append(
                    {
                        "url": url,
                        "status": "unhealthy",
                        "status_code": exc.code,
                        "error": str(exc),
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                results.append(
                    {
                        "url": url,
                        "status": "error",
                        "error": str(exc),
                    }
                )
        return results

    def detect_health_issues(self) -> list[dict[str, object]]:
        return [result for result in self.check_health() if result["status"] != "healthy"]

    def build_incident_triggers(
        self,
        *,
        service: str,
        repo: str,
        branch: str,
    ) -> list[IncidentTrigger]:
        triggers: list[IncidentTrigger] = []
        detected_at = datetime.now(timezone.utc).isoformat()
        for issue in self.detect_health_issues():
            triggers.append(
                IncidentTrigger(
                    source="healthcheck",
                    service=service,
                    repo=repo,
                    branch=branch,
                    detected_at=detected_at,
                    metadata={"healthcheck_issue": issue},
                )
            )
        return triggers
