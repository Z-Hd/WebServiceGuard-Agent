"""Developer-profile lookup helpers for personalized third-stage notifications."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_ROOT = Path(__file__).resolve().parents[1] / "developer_profiles"


@dataclass(slots=True)
class DeveloperProfileResolution:
    """Resolved notification-persona profile for a delivery target."""

    profile: dict[str, Any]
    source_path: str | None
    matched_by: str
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": dict(self.profile),
            "source_path": self.source_path,
            "matched_by": self.matched_by,
            "errors": list(self.errors),
        }


class DeveloperProfileService:
    """Resolve a developer-notification profile from local Markdown profile files."""

    def __init__(self, *, profile_root: Path | None = None) -> None:
        self._profile_root = profile_root or PROFILE_ROOT

    def resolve_profile(
        self,
        *,
        prepared_task: Any,
        repair_result: dict[str, Any],
    ) -> DeveloperProfileResolution:
        errors: list[str] = []
        bug_event = _extract_bug_event(prepared_task)
        service_name = str(bug_event.get("service", "")).strip()
        profiles = self._load_profiles(errors)
        if not profiles:
            default_profile = self._build_builtin_default_profile()
            return DeveloperProfileResolution(
                profile=default_profile,
                source_path=None,
                matched_by="builtin_default",
                errors=errors,
            )

        if service_name:
            for profile, source_path in profiles:
                single_service = str(profile.get("service", "")).strip()
                service_aliases = [
                    str(item).strip()
                    for item in (profile.get("services") or [])
                    if str(item).strip()
                ]
                if service_name == single_service or service_name in service_aliases:
                    return DeveloperProfileResolution(
                        profile=profile,
                        source_path=str(source_path),
                        matched_by="service",
                        errors=errors,
                    )

        default_entry = next(
            (
                (profile, source_path)
                for profile, source_path in profiles
                if str(profile.get("id", "")).strip() == "default"
            ),
            None,
        )
        if default_entry is not None:
            profile, source_path = default_entry
            return DeveloperProfileResolution(
                profile=profile,
                source_path=str(source_path),
                matched_by="default_profile",
                errors=errors,
            )

        fallback_profile, fallback_path = profiles[0]
        errors.append("No default profile was found; falling back to the first available profile.")
        return DeveloperProfileResolution(
            profile=fallback_profile,
            source_path=str(fallback_path),
            matched_by="first_available",
            errors=errors,
        )

    def _load_profiles(self, errors: list[str]) -> list[tuple[dict[str, Any], Path]]:
        if not self._profile_root.exists():
            errors.append(f"Profile root does not exist: {self._profile_root}")
            return []
        if not self._profile_root.is_dir():
            errors.append(f"Profile root is not a directory: {self._profile_root}")
            return []

        profiles: list[tuple[dict[str, Any], Path]] = []
        for path in sorted(self._profile_root.glob("*.md")):
            try:
                profile = self._parse_profile_file(path)
            except ValueError as exc:
                errors.append(f"{path}: {exc}")
                continue
            profiles.append((profile, path))
        return profiles

    def _parse_profile_file(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        front_matter, body = _split_front_matter(text)
        profile = _parse_front_matter(front_matter)
        profile["notes"] = body.strip()
        if "id" not in profile or not str(profile["id"]).strip():
            raise ValueError("Profile front matter must define a non-empty `id`.")
        return profile

    def _build_builtin_default_profile(self) -> dict[str, Any]:
        return {
            "id": "default",
            "language": "zh-CN",
            "tone": "concise",
            "verbosity": "short",
            "opening_style": "neutral",
            "emoji_level": "low",
            "format_preferences": ["summary-first", "root-cause", "verification", "action-item"],
            "preferred_sections": ["conclusion", "root-cause", "verification", "action-item", "pr-link"],
            "action_style": "explicit",
            "avoid": ["excessive-apology", "vague-language"],
            "notes": "Use a concise factual notification with clear action guidance.",
        }


def _split_front_matter(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Profile Markdown must begin with `---` front matter.")
    end_index = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = idx
            break
    if end_index is None:
        raise ValueError("Profile front matter is missing a closing `---` line.")
    front_matter = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1:])
    return front_matter, body


def _parse_front_matter(front_matter: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    active_list_key: str | None = None
    for raw_line in front_matter.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith((" ", "\t")):
            stripped = raw_line.strip()
            if active_list_key is None or not stripped.startswith("- "):
                raise ValueError(f"Unsupported front matter line: {raw_line}")
            result.setdefault(active_list_key, []).append(_parse_scalar(stripped[2:].strip()))
            continue

        active_list_key = None
        if ":" not in raw_line:
            raise ValueError(f"Unsupported front matter line: {raw_line}")
        key, raw_value = raw_line.split(":", 1)
        normalized_key = key.strip()
        value = raw_value.strip()
        if not normalized_key:
            raise ValueError("Front matter contains an empty key.")
        if value == "":
            result[normalized_key] = []
            active_list_key = normalized_key
            continue
        result[normalized_key] = _parse_scalar(value)
    return result


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _extract_bug_event(prepared_task: Any) -> dict[str, Any]:
    repair_task = getattr(prepared_task, "repair_task", None)
    if repair_task is not None:
        bug_event = getattr(repair_task, "bug_event", None)
        if bug_event is not None and hasattr(bug_event, "to_dict"):
            return bug_event.to_dict()
    if isinstance(prepared_task, dict):
        return dict((prepared_task.get("repair_task") or {}).get("bug_event") or {})
    return {}
