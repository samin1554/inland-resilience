"""Cache + last-known-good snapshots (ADR-006).

`MemoryCacheStore` is for tests and local runs. A PostGIS-backed store (on S7's provider_fetches /
cached_evidence tables) implements the same protocol later; nothing else changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from inland_worker.contracts.models import Evidence


class CacheEntry(BaseModel):
    provider_id: str
    cache_key: str
    items: list[Evidence]
    fetched_at: datetime
    expires_at: datetime

    def is_fresh(self, now: datetime) -> bool:
        return now < self.expires_at


class CacheStore(Protocol):
    def get(self, cache_key: str) -> CacheEntry | None:
        """Latest successful fetch for this key (it is also the last-known-good snapshot)."""

    def put(self, entry: CacheEntry) -> None:
        """Store a successful fetch; it becomes the last-known-good snapshot for its key."""


class MemoryCacheStore:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}

    def get(self, cache_key: str) -> CacheEntry | None:
        return self._entries.get(cache_key)

    def put(self, entry: CacheEntry) -> None:
        self._entries[entry.cache_key] = entry

    def clear(self) -> None:
        self._entries.clear()
