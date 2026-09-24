"""inland_data: the one way to read data. Callers never talk to providers.

Resolution order for get_evidence():
  1. cache hit and fresh            → origin="cache",    Fresh
  2. otherwise fetch live           → origin="live",     Fresh   (stored as the new last-known-good)
  3. live fails, snapshot exists    → origin="snapshot", Stale   (every item flagged `stale_snapshot`)
  4. live fails, nothing cached     → origin="none",     Missing (no items: "insufficient evidence")
In fixture mode (INLAND_DATA_MODE=fixture) recorded responses are used instead of the network.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from inland_worker.connectors.registry import get_connector
from inland_worker.contracts.models import DateRange, Evidence
from inland_worker.data.cache import CacheEntry, CacheStore, MemoryCacheStore
from inland_worker.data.trace import MemoryTraceSink, ToolExecution, TraceSink
from inland_worker.kit.config import ProviderRegistry, load_providers
from inland_worker.kit.connector import BaseConnector, BBox
from inland_worker.kit.errors import ProviderError
from inland_worker.kit.fixtures import FixtureStore
from inland_worker.kit.http import KitHttpClient
from inland_worker.kit.runner import Mode, data_mode, fetch

STALE_FLAG = "stale_snapshot"


class Fresh(BaseModel):
    kind: Literal["fresh"] = "fresh"


class Stale(BaseModel):
    kind: Literal["stale"] = "stale"
    age_s: int
    reason: str


class Missing(BaseModel):
    kind: Literal["missing"] = "missing"
    reason: str


Freshness = Fresh | Stale | Missing


class EvidenceResult(BaseModel):
    provider_id: str
    items: list[Evidence]
    freshness: Freshness
    origin: Literal["cache", "live", "snapshot", "fixture", "none"]
    cache_key: str
    fetched_at: datetime | None

    @property
    def ok(self) -> bool:
        return not isinstance(self.freshness, Missing)


def cache_key(provider_id: str, fields: list[str], values: dict[str, Any]) -> str:
    chosen = {f: values.get(f) for f in fields} if fields else values
    blob = json.dumps({"provider": provider_id, **chosen}, sort_keys=True, default=str)
    return f"{provider_id}:{hashlib.sha256(blob.encode()).hexdigest()[:16]}"


class DataService:
    def __init__(
        self,
        *,
        registry: ProviderRegistry | None = None,
        cache: CacheStore | None = None,
        trace: TraceSink | None = None,
        mode: Mode | None = None,
        fixtures: FixtureStore | None = None,
        client_factory: Callable[[BaseConnector], KitHttpClient] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.registry = registry or load_providers()
        self.cache = cache or MemoryCacheStore()
        self.trace = trace or MemoryTraceSink()
        self.mode = mode
        self.fixtures = fixtures or FixtureStore()
        self.client_factory = client_factory or (lambda c: KitHttpClient(c.config))
        self.clock = clock

    async def get_evidence(
        self,
        provider_id: str,
        *,
        area: dict[str, Any] | None = None,
        bbox: BBox | None = None,
        date_range: DateRange | dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        job_id: str | None = None,
        force_live: bool = False,
        fixture_case: str = "success",
    ) -> EvidenceResult:
        connector = get_connector(provider_id, self.registry)
        if area is None and bbox is None and connector.config.ingestion.default_area:
            bbox = self.registry.area_bbox(connector.config.ingestion.default_area)
        query = connector.query(area=area, bbox=bbox, date_range=date_range, params=params)
        key = cache_key(provider_id, connector.config.cache.key, query.cache_fields())
        started = self.clock()
        mode = self.mode or data_mode()

        result: EvidenceResult
        error_code: str | None = None
        if mode == "fixture":
            fetched = await fetch(connector, query, mode="fixture", case=fixture_case, fixtures=self.fixtures)
            result = EvidenceResult(
                provider_id=provider_id,
                items=fetched.items,
                freshness=Fresh(),
                origin="fixture",
                cache_key=key,
                fetched_at=started,
            )
        else:
            entry = self.cache.get(key)
            if entry and entry.is_fresh(started) and not force_live:
                result = EvidenceResult(
                    provider_id=provider_id,
                    items=entry.items,
                    freshness=Fresh(),
                    origin="cache",
                    cache_key=key,
                    fetched_at=entry.fetched_at,
                )
            else:
                try:
                    fetched = await fetch(
                        connector, query, mode="live", client=self.client_factory(connector)
                    )
                    now = self.clock()
                    self.cache.put(
                        CacheEntry(
                            provider_id=provider_id,
                            cache_key=key,
                            items=fetched.items,
                            fetched_at=now,
                            expires_at=now + timedelta(seconds=connector.config.cache.ttl),
                        )
                    )
                    result = EvidenceResult(
                        provider_id=provider_id,
                        items=fetched.items,
                        freshness=Fresh(),
                        origin="live",
                        cache_key=key,
                        fetched_at=now,
                    )
                except ProviderError as exc:
                    error_code = exc.code
                    if entry is not None:
                        age = int((started - entry.fetched_at).total_seconds())
                        result = EvidenceResult(
                            provider_id=provider_id,
                            items=[i.with_flag(STALE_FLAG) for i in entry.items],
                            freshness=Stale(age_s=age, reason=exc.code),
                            origin="snapshot",
                            cache_key=key,
                            fetched_at=entry.fetched_at,
                        )
                    else:
                        result = EvidenceResult(
                            provider_id=provider_id,
                            items=[],
                            freshness=Missing(reason=exc.code),
                            origin="none",
                            cache_key=key,
                            fetched_at=None,
                        )

        if job_id is not None:
            result.items = [i.model_copy(update={"job_id": job_id}) for i in result.items]
        self._trace(provider_id, query.cache_fields(), result, job_id, started, error_code)
        return result

    async def get_reference_layer(self, provider_id: str, **kwargs: Any) -> dict[str, Any]:
        """A provider's current data as a GeoJSON FeatureCollection (e.g. the county boundary)."""
        result = await self.get_evidence(provider_id, **kwargs)
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": i.id,
                    "geometry": i.geometry.model_dump() if i.geometry else None,
                    "properties": {
                        **i.properties,
                        "observed_at": i.observed_at.isoformat(),
                        "source": i.source,
                        "quality_flags": i.quality_flags,
                    },
                }
                for i in result.items
            ],
            "freshness": result.freshness.model_dump(),
        }

    def _trace(
        self,
        provider_id: str,
        inputs: dict[str, Any],
        result: EvidenceResult,
        job_id: str | None,
        started: datetime,
        error_code: str | None,
    ) -> None:
        status = {"fresh": "ok", "stale": "stale", "missing": "missing"}[result.freshness.kind]
        self.trace.record(
            ToolExecution(
                job_id=job_id,
                tool_name=f"get_evidence:{provider_id}",
                input=inputs,
                output_summary={
                    "count": len(result.items),
                    "origin": result.origin,
                    "freshness": result.freshness.model_dump(),
                },
                started_at=started,
                completed_at=self.clock(),
                status=status,
                error_code=error_code,
            )
        )


_default: DataService | None = None


def default_service() -> DataService:
    global _default
    if _default is None:
        _default = DataService()
    return _default


async def get_evidence(provider_id: str, **kwargs: Any) -> EvidenceResult:
    """One line to get any source: `await get_evidence("firms", area=aoi, date_range=dates)`."""
    return await default_service().get_evidence(provider_id, **kwargs)


async def get_reference_layer(provider_id: str, **kwargs: Any) -> dict[str, Any]:
    return await default_service().get_reference_layer(provider_id, **kwargs)
