from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from web_service_guard.config import config
from web_service_guard.schemas.traceback_candidate import TracebackCandidate


TRACEBACK_START_MARKER = "Traceback (most recent call last):"


class TracebackCollector:
    """Collect traceback candidates from log files."""

    def __init__(
        self,
        *,
        log_path: str | None = None,
        log_pattern: str | None = None,
        check_interval: int | None = None,
        max_log_size: int | None = None,
    ) -> None:
        self.log_path = log_path or config.log_path
        self.log_pattern = log_pattern or config.get("monitor_log_pattern")
        self.check_interval = check_interval or config.get("monitor_check_interval", 10)
        self.max_log_size = max_log_size or config.get("monitor_max_log_size", 1_048_576)
        self.last_check_time = time.time()

    def collect_tracebacks(
        self,
        *,
        service: str | None = None,
        source: str = "log",
        detected_at: str | None = None,
    ) -> list[TracebackCandidate]:
        """Collect structured traceback candidates from the configured log file."""

        log_text = self._read_log_text()
        if not log_text:
            return []
        blocks = self._extract_traceback_blocks(log_text)
        discovered_at = detected_at or _utc_now()
        candidates: list[TracebackCandidate] = []
        for block in blocks:
            normalized = self._normalize_block(block)
            if not normalized:
                continue
            candidates.append(
                TracebackCandidate(
                    raw_text=normalized,
                    source=source,
                    detected_at=discovered_at,
                    fingerprint=self._build_fingerprint(normalized),
                    service=service,
                )
            )
        return candidates

    def collect_traceback_texts(self, **kwargs: object) -> list[str]:
        """Compatibility helper returning only raw traceback text blocks."""

        return [candidate.raw_text for candidate in self.collect_tracebacks(**kwargs)]

    def check_new_errors(
        self,
        *,
        service: str | None = None,
        source: str = "log",
    ) -> list[TracebackCandidate]:
        """Poll on an interval and return new traceback candidates when due."""

        current_time = time.time()
        if current_time - self.last_check_time < self.check_interval:
            return []
        self.last_check_time = current_time
        return self.collect_tracebacks(service=service, source=source)

    def _read_log_text(self) -> str:
        path = Path(self.log_path)
        if not path.exists() or path.is_dir():
            return ""
        try:
            file_size = path.stat().st_size
            if file_size > self.max_log_size:
                with path.open("rb") as handle:
                    seek_offset = max(0, file_size - self.max_log_size)
                    handle.seek(seek_offset)
                    if seek_offset > 0:
                        # Drop the first partial line so traceback parsing starts on a line boundary.
                        handle.readline()
                    raw = handle.read()
            else:
                raw = path.read_bytes()
        except OSError:
            return ""
        return raw.decode("utf-8", errors="ignore")

    def _extract_traceback_blocks(self, log_text: str) -> list[str]:
        lines = log_text.splitlines()
        blocks: list[str] = []
        current: list[str] = []
        capturing = False

        for line in lines:
            if TRACEBACK_START_MARKER in line:
                if current:
                    blocks.append("\n".join(current))
                current = [line]
                capturing = True
                continue

            if not capturing:
                continue

            current.append(line)
            if self._looks_like_terminal_exception(line):
                blocks.append("\n".join(current))
                current = []
                capturing = False

        if current:
            blocks.append("\n".join(current))

        if not self.log_pattern:
            return blocks
        pattern = re.compile(self.log_pattern, re.IGNORECASE)
        return [block for block in blocks if pattern.search(block)]

    def _normalize_block(self, block: str) -> str:
        lines = [line.rstrip() for line in block.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _build_fingerprint(self, normalized_block: str) -> str:
        return hashlib.sha256(normalized_block.encode("utf-8")).hexdigest()[:16]

    def _looks_like_terminal_exception(self, line: str) -> bool:
        stripped = line.strip()
        return bool(
            re.match(
                r"^[A-Za-z_][\w.]*?(Error|Exception|Failure|Fault|Exit)(:|$)",
                stripped,
            )
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
