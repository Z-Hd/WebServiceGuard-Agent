"""Small in-memory dedup store for first-phase event fingerprints."""

from __future__ import annotations

from datetime import datetime, timezone


class InMemoryDedupStore:
    """Deduplicate repeated incidents within a configurable TTL window."""

    def __init__(self, *, ttl_sec: int = 3600) -> None:
        self._ttl_sec = ttl_sec
        self._seen: dict[str, float] = {}

    def is_duplicate(self, fingerprint: str, *, seen_at: str | None = None) -> bool:
        self._evict_expired()
        timestamp = self._to_epoch(seen_at)
        previous = self._seen.get(fingerprint)
        if previous is not None and timestamp - previous < self._ttl_sec:
            return True
        self._seen[fingerprint] = timestamp
        return False

    def _evict_expired(self) -> None:
        if not self._seen:
            return
        now_epoch = self._to_epoch(None)
        expired = [key for key, ts in self._seen.items() if now_epoch - ts >= self._ttl_sec]
        for key in expired:
            self._seen.pop(key, None)

    def _to_epoch(self, timestamp: str | None) -> float:
        if not timestamp:
            return datetime.now(timezone.utc).timestamp()
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return datetime.now(timezone.utc).timestamp()
