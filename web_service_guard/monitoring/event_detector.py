<<<<<<< HEAD
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

from web_service_guard.schemas.bug_event import BugEvent
from web_service_guard.schemas.traceback_candidate import TracebackCandidate


TERMINAL_ERROR_PATTERN = re.compile(
    r"^(?P<error_type>[A-Za-z_][\w.]*?(?:Error|Exception|Failure|Fault|Exit))(?::\s*(?P<message>.*))?$"
)
FILE_LINE_PATTERN = re.compile(r'File "(?P<file>.*?)", line (?P<line>\d+)')


class EventDetector:
    """Normalize traceback candidates into stable BugEvent objects."""

    def detect_events(
        self,
        tracebacks: Iterable[str | TracebackCandidate],
        service: str,
        repo: str,
        branch: str,
        *,
        source: str | None = None,
        detected_at: str | None = None,
    ) -> list[BugEvent]:
        events: list[BugEvent] = []
        for candidate in self._coerce_candidates(
            tracebacks,
            service=service,
            source=source,
            detected_at=detected_at,
        ):
            error_info = self.extract_error_info(candidate.raw_text)
            event_detected_at = candidate.detected_at or detected_at or _utc_now()
            events.append(
                BugEvent(
                    event_id=self._build_event_id(candidate.fingerprint, event_detected_at),
                    source=source or candidate.source,
                    service=service,
                    repo=repo,
                    branch=branch,
                    detected_at=event_detected_at,
                    occurred_at=candidate.metadata.get("occurred_at"),
                    error_type=error_info["error_type"],
                    error_message=error_info["error_message"],
                    error_summary=self._build_error_summary(
                        error_info["error_type"],
                        error_info["error_message"],
                    ),
                    traceback=candidate.raw_text,
                    fingerprint=candidate.fingerprint,
                    primary_file=error_info["file_path"] or None,
                    primary_line=error_info["line_number"],
                    metadata=dict(candidate.metadata),
                )
            )
        return events

    def extract_error_info(self, error_log: str) -> dict[str, object]:
        """Extract terminal error information and primary source location."""

        lines = [line.strip() for line in error_log.splitlines() if line.strip()]
        terminal_line = ""
        for line in reversed(lines):
            if TERMINAL_ERROR_PATTERN.match(line):
                terminal_line = line
                break
        if not terminal_line and lines:
            terminal_line = lines[-1]

        match = TERMINAL_ERROR_PATTERN.match(terminal_line)
        if match:
            error_type = match.group("error_type")
            error_message = (match.group("message") or "").strip()
        else:
            error_type = "UnknownError"
            error_message = terminal_line

        file_matches = list(FILE_LINE_PATTERN.finditer(error_log))
        file_path = file_matches[-1].group("file") if file_matches else ""
        line_number = int(file_matches[-1].group("line")) if file_matches else None

        return {
            "error_type": error_type,
            "error_message": error_message,
            "traceback": error_log,
            "file_path": file_path,
            "line_number": line_number,
        }

    def _coerce_candidates(
        self,
        tracebacks: Iterable[str | TracebackCandidate],
        *,
        service: str,
        source: str | None,
        detected_at: str | None,
    ) -> list[TracebackCandidate]:
        candidates: list[TracebackCandidate] = []
        for item in tracebacks:
            if isinstance(item, TracebackCandidate):
                candidates.append(item)
                continue
            raw_text = str(item).strip()
            if not raw_text:
                continue
            discovered_at = detected_at or _utc_now()
            candidates.append(
                TracebackCandidate(
                    raw_text=raw_text,
                    source=source or "log",
                    detected_at=discovered_at,
                    fingerprint=hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16],
                    service=service,
                )
            )
        return candidates

    def _build_error_summary(self, error_type: str, error_message: str) -> str:
        summary = error_type if not error_message else f"{error_type}: {error_message}"
        return summary[:160]

    def _build_event_id(self, fingerprint: str, detected_at: str) -> str:
        compact_time = detected_at.replace("-", "").replace(":", "").replace(".", "")
        compact_time = compact_time.replace("+0000", "Z").replace("+00:00", "Z")
        return f"evt_{fingerprint}_{compact_time}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
=======
import re
from web_service_guard.schemas.event import BugEvent
from datetime import datetime

class EventDetector:
    """事件检测器"""
    def __init__(self):
        pass
    
    def detect_events(self, tracebacks, service, repo, branch):
        """检测错误并生成BugEvent"""
        events = []
        for traceback in tracebacks:
            # 提取错误信息
            error_info = self.extract_error_info(traceback)
            if error_info:
                # 生成BugEvent
                event = BugEvent(
                    service=service,
                    error_summary=f"{error_info['error_type']}: {error_info['error_message'][:50]}",
                    traceback=traceback,
                    timestamp=datetime.now().isoformat(),
                    repo=repo,
                    branch=branch
                )
                events.append(event)
        return events
    
    def extract_error_info(self, error_log):
        """从错误日志中提取错误信息"""
        # 提取错误类型
        error_type_match = re.search(r'([A-Za-z]+)Error:', error_log)
        error_type = error_type_match.group(1) if error_type_match else 'Unknown'
        
        # 提取错误消息
        error_message_match = re.search(r'Error: (.*)', error_log)
        error_message = error_message_match.group(1) if error_message_match else error_log
        
        # 提取 Traceback
        traceback_match = re.search(r'Traceback \(most recent call last\):(.*?)(?=[A-Za-z]+Error:|$)', error_log, re.DOTALL)
        traceback = traceback_match.group(1) if traceback_match else ''
        
        # 提取文件和行号
        file_line_match = re.search(r'File "(.*?)", line (\d+)', traceback)
        file_path = file_line_match.group(1) if file_line_match else ''
        line_number = file_line_match.group(2) if file_line_match else ''
        
        return {
            'error_type': error_type,
            'error_message': error_message,
            'traceback': traceback,
            'file_path': file_path,
            'line_number': line_number
        }
>>>>>>> a1ef785ad28bb576fdad597597c3fa90f22bfa28
