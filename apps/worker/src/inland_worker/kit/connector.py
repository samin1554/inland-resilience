"""The shape every connector fills in.

A connector is two pure methods (plus an optional third for follow-up requests):

    build_requests(query) -> list[ProviderRequest]     what to ask the provider
    follow(response, query) -> list[ProviderRequest]   next page / linked URL (optional)
    parse(responses, query) -> list[Evidence]          translate the answer into Evidence

The kit does all I/O: HTTP, auth, retries, size limits, fixtures and tracing. Connectors never import httpx.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import shape

from inland_worker.contracts.models import DateRange, Evidence, EvidenceType, Geometry
from inland_worker.kit.config import ProviderConfig
from inland_worker.kit.errors import ProviderParseError

BBox = tuple[float, float, float, float]  # west, south, east, north (WGS84)


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderQuery(BaseModel):
    """What the caller wants. `area` (GeoJSON geometry) or `bbox` must be given."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    area: dict[str, Any] | None = None
    bbox: BBox | None = None
    date_range: DateRange | None = None
    params: BaseModel = Field(default_factory=NoParams)

    @model_validator(mode="after")
    def _has_extent(self) -> ProviderQuery:
        if self.area is None and self.bbox is None:
            raise ValueError("ProviderQuery needs an area (GeoJSON geometry) or a bbox")
        if self.bbox is not None:
            w, s, e, n = self.bbox
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError(f"invalid bbox {self.bbox}; expected west<east, south<north in WGS84")
        return self

    def get_bbox(self) -> BBox:
        if self.bbox is not None:
            return self.bbox
        return tuple(round(v, 6) for v in shape(self.area).bounds)  # type: ignore[return-value]

    def representative_point(self) -> tuple[float, float]:
        """(lon, lat) guaranteed to lie inside the area (or the bbox centre)."""
        if self.area is not None:
            p = shape(self.area).representative_point()
            return (p.x, p.y)
        w, s, e, n = self.get_bbox()
        return ((w + e) / 2, (s + n) / 2)

    def cache_fields(self) -> dict[str, Any]:
        bbox = tuple(round(v, 3) for v in self.get_bbox())
        fields: dict[str, Any] = {"bbox": bbox}
        if self.date_range:
            fields["date_range"] = f"{self.date_range.start}/{self.date_range.end}"
        fields.update(self.params.model_dump(mode="json"))
        return fields


class ProviderRequest(BaseModel):
    """One HTTP request. Use `path` (appended to base_url) or `url` (absolute, e.g. a followed link).
    GET by default; POST with a `json` body for APIs like STAC search."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST"] = "GET"
    json_body: dict[str, Any] | None = None
    path: str = ""
    url: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    label: str = "main"
    expect: Literal["json", "text"] = "json"


class RawResponse(BaseModel):
    """A provider response as the connector sees it. `url` is always redacted."""

    model_config = ConfigDict(extra="forbid")

    request: ProviderRequest
    url: str
    status: int
    content_type: str | None = None
    body: bytes
    retrieved_at: datetime

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON. Raises ValueError (the runner turns it into ProviderParseError)."""
        return json.loads(self.body)


class BaseConnector(ABC):
    provider_id: ClassVar[str]
    evidence_types: ClassVar[frozenset[EvidenceType]]
    Params: ClassVar[type[BaseModel]] = NoParams

    def __init__(self, config: ProviderConfig):
        if config.provider_id != self.provider_id:
            raise ValueError(f"config for {config.provider_id!r} given to {type(self).__name__}")
        self.config = config

    # --- the parts a connector author writes -------------------------------------------------
    @abstractmethod
    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]: ...

    def follow(self, response: RawResponse, query: ProviderQuery) -> list[ProviderRequest]:
        """Return follow-up requests (next page, linked URL). Default: none."""
        return []

    @abstractmethod
    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]: ...

    # --- helpers -----------------------------------------------------------------------------
    def query(
        self,
        *,
        area: dict[str, Any] | None = None,
        bbox: BBox | None = None,
        date_range: DateRange | dict[str, Any] | None = None,
        params: dict[str, Any] | BaseModel | None = None,
    ) -> ProviderQuery:
        """Build a validated query; unknown or out-of-range params fail here, before any network call."""
        if not isinstance(params, BaseModel):
            params = self.Params.model_validate(params or {})
        if isinstance(date_range, dict):
            date_range = DateRange.model_validate(date_range)
        return ProviderQuery(area=area, bbox=bbox, date_range=date_range, params=params)

    def evidence(
        self,
        *,
        evidence_type: EvidenceType,
        observed_at: datetime,
        retrieved_at: datetime,
        geometry: dict[str, Any] | None,
        properties: dict[str, Any],
        source_record_id: str | None = None,
        quality_flags: Iterable[str] = (),
        extra_limitations: Iterable[str] = (),
    ) -> Evidence:
        """Create Evidence with this provider's source name, URL and default limitations filled in."""
        if observed_at.tzinfo is None or retrieved_at.tzinfo is None:
            raise ProviderParseError(self.provider_id, "observed_at and retrieved_at must be timezone-aware")
        flags = list(dict.fromkeys(quality_flags))
        limitations = list(dict.fromkeys([*self.config.default_limitations, *extra_limitations]))
        geom = Geometry.model_validate(geometry) if geometry else None
        # identity = provider record + time; geometry only when the provider gives no record ID
        identity = source_record_id or json.dumps(geom.model_dump() if geom else None, sort_keys=True)
        return Evidence(
            id=Evidence.stable_id(self.provider_id, identity, observed_at.isoformat()),
            evidence_type=evidence_type,
            source=self.config.display_name,
            source_record_id=source_record_id,
            observed_at=observed_at.astimezone(UTC),
            retrieved_at=retrieved_at.astimezone(UTC),
            geometry=geom,
            properties=properties,
            quality_flags=flags,
            limitations=limitations,
            source_url=self.config.source_url,
        )
