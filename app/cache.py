from __future__ import annotations

import copy
from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any

from pydantic import BaseModel

from app.runtime_metrics import RuntimeMetrics


class ExpiringCache:
    def __init__(
        self,
        *,
        name: str,
        max_entries: int,
        metrics: RuntimeMetrics | None = None,
    ) -> None:
        self.name = name
        self.max_entries = max_entries
        self.metrics = metrics
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = monotonic()
        with self._lock:
            expired = self._purge_expired(now)
            entry = self._entries.get(key)
            if entry is None:
                self._record(event="miss", expirations=expired)
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._entries.pop(key, None)
                self._record(event="miss", expirations=expired + 1)
                return None
            self._entries.move_to_end(key)
            self._record(event="hit", expirations=expired)
            return self._copy_value(value)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        with self._lock:
            expired = self._purge_expired(monotonic())
            if key in self._entries:
                self._entries.pop(key, None)
            self._entries[key] = (monotonic() + ttl_seconds, self._copy_value(value))
            evictions = 0
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
                evictions += 1
            self._record(event="set", evictions=evictions, expirations=expired)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._record(event="clear")

    @staticmethod
    def _copy_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_copy(deep=True)
        return copy.deepcopy(value)

    def _purge_expired(self, now: float) -> int:
        expired_keys = [
            key
            for key, (expires_at, _) in self._entries.items()
            if expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
        return len(expired_keys)

    def _record(
        self,
        *,
        event: str,
        evictions: int = 0,
        expirations: int = 0,
    ) -> None:
        if self.metrics is None:
            return
        self.metrics.record_cache_event(
            cache_name=self.name,
            event=event,
            current_size=len(self._entries),
            max_size=self.max_entries,
            evictions=evictions,
            expirations=expirations,
        )
