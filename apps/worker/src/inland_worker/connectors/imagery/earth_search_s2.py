"""Sentinel-2 L2A scene discovery via Earth Search (STAC), on AWS open data. No account or key.

REFERENCE CONNECTOR for the *STAC imagery* pattern (ADR-009). Copy it for Landsat and other STAC collections:
    make new-connector NAME=<id> GROUP=imagery PATTERN=stac

This connector only *finds* imagery: one `satellite_measurement` evidence item per acquisition date, listing the
scenes (tiles) that cover the area and where their bands live. Reading pixels is `kit/imagery.py`'s job.

What makes this pattern tricky, and how it's handled here:
- STAC search is a POST with a JSON body; paging is a `next` link that is also a POST (see `follow`).
- The same tile can appear twice on one date (e.g. Sentinel-2A and 2C passing the same day): keep the least
  cloudy one per tile.
- Whether the -0.1 reflectance offset is already applied differs per scene (`earthsearch:boa_offset_applied`):
  it's recorded per scene here, and kit/imagery.py applies it correctly.
Spec: docs/connectors/providers/earth-search-s2.md
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from shapely import make_valid
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse

COLLECTION = "sentinel-2-l2a"
BANDS = ("red", "nir", "swir22", "scl", "visual")  # what kit/imagery.py and S6 need


class EarthSearchS2Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloud_limit: float = Field(default=20, ge=0, le=100, description="max scene-level cloud cover (%)")
    page_size: int = Field(default=50, ge=1, le=100)


class EarthSearchS2Connector(BaseConnector):
    provider_id = "earth_search_s2"
    evidence_types = frozenset({EvidenceType.SATELLITE_MEASUREMENT})
    Params = EarthSearchS2Params

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        if query.date_range is None:
            raise ValueError("earth_search_s2 needs a date_range (a window to search for scenes)")
        p: EarthSearchS2Params = query.params  # type: ignore[assignment]
        dr = query.date_range
        body = {
            "collections": [COLLECTION],
            "bbox": list(query.get_bbox()),
            "datetime": f"{dr.start}T00:00:00Z/{dr.end}T23:59:59Z",
            "limit": p.page_size,
            "query": {"eo:cloud_cover": {"lte": p.cloud_limit}},
            "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        }
        return [ProviderRequest(method="POST", path="/search", json_body=body, label="search")]

    def follow(self, response: RawResponse, query: ProviderQuery) -> list[ProviderRequest]:
        label = response.request.label
        page = int(label.removeprefix("page_")) + 1 if label.startswith("page_") else 2
        for link in response.json().get("links", []):
            if link.get("rel") == "next":  # STAC paging: re-send the body the server gives us
                return [
                    ProviderRequest(
                        method=link.get("method", "GET"),
                        url=link["href"],
                        json_body=link.get("body"),
                        label=f"page_{page}",
                    )
                ]
        return []

    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]:
        aoi = make_valid(shape(query.area)) if query.area else box(*query.get_bbox())
        by_date: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        retrieved_at = max(r.retrieved_at for r in responses)
        for resp in responses:
            for item in resp.json()["features"]:
                props = item["properties"]
                date = props["datetime"][:10]
                tile = props.get("grid:code") or item["id"].split("_")[1]
                current = by_date[date].get(tile)
                # one scene per tile per date: keep the least cloudy (ties: lowest id, for determinism)
                if current is None or (props.get("eo:cloud_cover", 100), item["id"]) < (
                    current["properties"].get("eo:cloud_cover", 100),
                    current["id"],
                ):
                    by_date[date][tile] = item
        return [
            self._date_evidence(date, list(tiles.values()), aoi, retrieved_at)
            for date, tiles in sorted(by_date.items())
        ]

    def _date_evidence(self, date: str, items: list[dict[str, Any]], aoi, retrieved_at: datetime) -> Evidence:
        footprint = unary_union([make_valid(shape(i["geometry"])) for i in items])
        coverage = round(float(footprint.intersection(aoi).area / aoi.area), 4) if aoi.area else 0.0
        scenes = []
        for i in sorted(items, key=lambda x: x["id"]):
            props = i["properties"]
            scenes.append(
                {
                    "id": i["id"],
                    "tile": props.get("grid:code"),
                    "platform": props.get("platform"),
                    "acquired_at": props["datetime"],
                    "cloud_cover_pct": props.get("eo:cloud_cover"),
                    "processing_baseline": props.get("s2:processing_baseline"),
                    "boa_offset_applied": bool(props.get("earthsearch:boa_offset_applied")),
                    "assets": {
                        band: {
                            "href": i["assets"][band]["href"],
                            **{
                                k: v
                                for k, v in (i["assets"][band].get("raster:bands") or [{}])[0].items()
                                if k in ("scale", "offset", "nodata", "spatial_resolution")
                            },
                        }
                        for band in BANDS
                        if band in i["assets"]
                    },
                }
            )
        flags = []
        if coverage < 0.99:
            flags.append("partial_aoi_coverage")
        missing = [b for b in BANDS if any(b not in s["assets"] for s in scenes)]
        if missing:
            flags.append("missing_bands")
        observed = min(datetime.fromisoformat(s["acquired_at"].replace("Z", "+00:00")) for s in scenes)
        return self.evidence(
            evidence_type=EvidenceType.SATELLITE_MEASUREMENT,
            observed_at=observed,
            retrieved_at=retrieved_at,
            geometry=mapping(footprint),
            source_record_id=f"{COLLECTION}:{date}:{','.join(s['id'] for s in scenes)}",
            properties={
                "collection": COLLECTION,
                "date": date,
                "aoi_coverage": coverage,
                "scene_cloud_max_pct": max((s["cloud_cover_pct"] or 0) for s in scenes),
                "scenes": scenes,
                "bands": list(BANDS),
            },
            quality_flags=flags,
        )
