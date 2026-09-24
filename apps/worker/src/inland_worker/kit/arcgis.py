"""Helpers for ArcGIS Feature Services (WFIGS, CAL FIRE, county layers, hazard zones).

- `query_request()` builds a paged /query request.
- `next_page()` returns the request for the next page when the service says there is more.
- `esri_to_geojson()` converts Esri JSON geometry (f=json) to GeoJSON.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from inland_worker.kit.connector import BBox, ProviderRequest, RawResponse


def query_request(
    *,
    bbox: BBox,
    out_fields: list[str] | str = "*",
    where: str = "1=1",
    fmt: str = "geojson",
    page_size: int = 1000,
    offset: int = 0,
    label: str = "page",
) -> ProviderRequest:
    fields = out_fields if isinstance(out_fields, str) else ",".join(out_fields)
    return ProviderRequest(
        path="/query",
        label=label,
        params={
            "where": where,
            "geometry": ",".join(f"{v:.6f}" for v in bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "OBJECTID",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
            "f": fmt,
        },
    )


def exceeded_transfer_limit(payload: dict[str, Any]) -> bool:
    # f=json puts the flag at the top level; f=geojson puts it under "properties"
    return bool(
        payload.get("exceededTransferLimit") or (payload.get("properties") or {}).get("exceededTransferLimit")
    )


def next_page(response: RawResponse) -> ProviderRequest | None:
    payload = response.json()
    if not isinstance(payload, dict) or not exceeded_transfer_limit(payload):
        return None
    params = dict(response.request.params)
    offset = int(params.get("resultOffset", "0")) + int(params.get("resultRecordCount", "1000"))
    params["resultOffset"] = str(offset)
    return response.request.model_copy(update={"params": params, "label": f"page_{offset}"})


def epoch_ms(value: Any) -> datetime | None:
    """ArcGIS dates are epoch milliseconds (UTC)."""
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def _signed_area(ring: list[list[float]]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1, *_), (x2, y2, *_) in pairwise(ring)) / 2


def esri_to_geojson(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert an Esri JSON geometry to GeoJSON. Esri outer rings are clockwise, holes counter-clockwise."""
    if not geometry:
        return None
    if "x" in geometry and "y" in geometry:
        return {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
    if "points" in geometry:
        return {"type": "MultiPoint", "coordinates": geometry["points"]}
    if "paths" in geometry:
        paths = geometry["paths"]
        if len(paths) == 1:
            return {"type": "LineString", "coordinates": paths[0]}
        return {"type": "MultiLineString", "coordinates": paths}
    if "rings" in geometry:
        polygons: list[list[list[list[float]]]] = []
        holes: list[list[list[float]]] = []
        for ring in geometry["rings"]:
            if _signed_area(ring) < 0:  # clockwise → outer ring
                polygons.append([ring])
            else:
                holes.append(ring)
        if not polygons and holes:  # badly wound data: treat everything as outer rings
            polygons, holes = [[h] for h in holes], []
        for hole in holes:
            from shapely.geometry import Point, Polygon

            probe = Point(hole[0][:2])
            owner = next((p for p in polygons if Polygon(p[0]).contains(probe)), polygons[0])
            owner.append(hole)
        if len(polygons) == 1:
            return {"type": "Polygon", "coordinates": polygons[0]}
        return {"type": "MultiPolygon", "coordinates": polygons}
    raise ValueError(f"unsupported Esri geometry keys: {sorted(geometry)}")
