"""STAC imagery: read satellite pixels for an area, correctly. Reference for the *STAC imagery* pattern (ADR-009).

The `earth_search_s2` connector finds scenes (one Evidence item per acquisition date). This module reads their
pixels for an area of interest (AOI):

    from inland_worker.kit.imagery import aoi_grid, pick_scene, read_bands

    scenes = (await get_evidence("earth_search_s2", area=aoi, date_range=window)).items
    grid = aoi_grid(aoi)                           # UTM grid over the (repaired) AOI, 20 m by default
    stack = read_bands(pick_scene(scenes), grid, bands=("nir", "swir22"))
    stack.arrays["nir"]                            # float32 reflectance, NaN where cloudy / no data
    stack.valid_pct_inside                         # usable share of the AOI

Lessons from the Line Fire proof of concept (docs/research/line-fire-2024), built in:
1. Reflectance = DN x scale + offset, **but the offset only if `boa_offset_applied` is false, per scene**.
2. One scene per tile per date (the connector already picks the least cloudy).
3. AOIs are repaired (`make_valid`) before use; perimeters from providers can be invalid.
4. Only the AOI window is read from each image file (COG range requests), never whole scenes.
Image URLs must be https on the provider's allowed_hosts, the same rule as every other provider call.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

from inland_worker.contracts.models import Evidence
from inland_worker.kit.config import ProviderConfig, load_providers
from inland_worker.kit.errors import HostNotAllowed, ProviderError, ProviderParseError

PROVIDER_ID = "earth_search_s2"
# Sentinel-2 scene classification (SCL) values treated as unusable:
# 0 no data, 1 saturated/defective, 3 cloud shadow, 8 cloud medium, 9 cloud high, 10 thin cirrus
DEFAULT_BAD_SCL = frozenset({0, 1, 3, 8, 9, 10})


@dataclass
class AoiGrid:
    """A regular grid in the AOI's UTM zone. `inside` marks pixels inside the AOI polygon."""

    crs: str
    transform: Affine
    width: int
    height: int
    res: float
    inside: np.ndarray
    area_ll: BaseGeometry

    @property
    def pixel_area_m2(self) -> float:
        return self.res * self.res


@dataclass
class BandStack:
    """Reflectance arrays on an AoiGrid. Masked pixels (cloud, shadow, no data) are NaN in every band."""

    arrays: dict[str, np.ndarray]
    valid: np.ndarray
    grid: AoiGrid
    scene_ids: list[str]
    acquired_at: datetime
    offsets_applied: dict[str, bool] = field(default_factory=dict)

    @property
    def valid_pct_inside(self) -> float:
        inside = self.grid.inside
        return round(100 * float((self.valid & inside).sum()) / max(int(inside.sum()), 1), 2)


def utm_crs_for(geom: BaseGeometry) -> str:
    """UTM zone of the geometry's centroid (WGS84 lon/lat in), e.g. San Bernardino → EPSG:32611."""
    c = geom.centroid
    zone = min(60, max(1, math.floor((c.x + 180) / 6) + 1))
    return f"EPSG:{(32600 if c.y >= 0 else 32700) + zone}"


def repair(area: Mapping[str, Any] | BaseGeometry) -> BaseGeometry:
    """Lesson 3: make the AOI valid, keeping only its polygon parts."""
    geom = area if isinstance(area, BaseGeometry) else shape(area)
    fixed = make_valid(geom)
    if fixed.geom_type == "GeometryCollection":
        polys = [g for g in fixed.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        fixed = unary_union(polys) if polys else fixed
    if fixed.is_empty or fixed.area == 0:
        raise ValueError("area is empty or has no area after repair")
    return fixed


def aoi_grid(area: Mapping[str, Any] | BaseGeometry, res: float = 20.0, buffer_m: float = 0.0) -> AoiGrid:
    """Build a UTM grid covering the (repaired) AOI. 20 m matches Sentinel-2's SWIR and SCL bands."""
    area_ll = repair(area)
    crs = utm_crs_for(area_ll)
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    area_utm = shp_transform(to_utm, area_ll)
    minx, miny, maxx, maxy = area_utm.buffer(buffer_m).bounds if buffer_m else area_utm.bounds
    width, height = max(1, math.ceil((maxx - minx) / res)), max(1, math.ceil((maxy - miny) / res))
    transform = from_origin(minx, maxy, res, res)
    inside = ~geometry_mask([mapping(area_utm)], out_shape=(height, width), transform=transform)
    return AoiGrid(
        crs=crs, transform=transform, width=width, height=height, res=res, inside=inside, area_ll=area_ll
    )


def pick_scene(
    scenes: Iterable[Evidence], *, min_coverage: float = 0.99, max_cloud_pct: float = 100
) -> Evidence | None:
    """The least-cloudy date that fully covers the AOI (scene-level cloud; SCL masking refines it later)."""
    ok = [
        s
        for s in scenes
        if s.properties.get("aoi_coverage", 0) >= min_coverage
        and s.properties.get("scene_cloud_max_pct", 100) <= max_cloud_pct
    ]
    return min(ok, key=lambda s: (s.properties["scene_cloud_max_pct"], s.properties["date"]), default=None)


def check_href(href: str, config: ProviderConfig, *, allow_local: bool = False) -> None:
    """Image URLs follow the same allowlist rule as every provider request."""
    parsed = urlparse(href)
    if allow_local and parsed.scheme in ("", "file"):
        return
    if parsed.scheme != "https" or parsed.hostname not in config.allowed_hosts:
        raise HostNotAllowed(config.provider_id, f"refusing to read {parsed.scheme}://{parsed.hostname}")


def _gdal_env(config: ProviderConfig) -> rasterio.Env:
    return rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",  # don't list S3 "folders"
        AWS_NO_SIGN_REQUEST="YES",  # public open data
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_TIMEOUT=str(int(config.timeout_s)),
        GDAL_HTTP_MAX_RETRY=str(config.retries.max),
        GDAL_HTTP_RETRY_DELAY=str(max(config.retries.backoff_s, 0.5)),
        VSI_CACHE="TRUE",
    )


def _reflectance_scale(asset: Mapping[str, Any], offset_applied: bool) -> tuple[float, float]:
    """Lesson 1: the offset is only added when the provider has NOT already applied it to the pixel values."""
    scale = float(asset.get("scale", 1.0))
    offset = 0.0 if offset_applied else float(asset.get("offset", 0.0))
    return scale, offset


def _resampling(band: str, asset: Mapping[str, Any], res: float) -> Resampling:
    if band == "scl":
        return Resampling.nearest  # classes must never be averaged
    src_res = float(asset.get("spatial_resolution", res))
    return Resampling.average if src_res < res else Resampling.bilinear


def _read_asset(
    href: str, grid: AoiGrid, band_index: int, resampling: Resampling, dtype=np.float32
) -> np.ndarray:
    out = np.zeros((grid.height, grid.width), dtype=dtype)
    with rasterio.open(href) as src:
        reproject(
            rasterio.band(src, band_index),
            out,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            resampling=resampling,
            src_nodata=0,
            dst_nodata=0,
        )
    return out


def read_bands(
    scene: Evidence,
    grid: AoiGrid,
    bands: Sequence[str] = ("nir", "swir22"),
    *,
    mask_clouds: bool = True,
    bad_scl: Iterable[int] = DEFAULT_BAD_SCL,
    config: ProviderConfig | None = None,
    allow_local: bool = False,
    trace: Any | None = None,
    job_id: str | None = None,
) -> BandStack:
    """Read reflectance for `bands` from one date's scenes onto `grid`, with clouds/no-data masked as NaN.
    Pass `trace` (a TraceSink) to record the read in tool_executions."""
    started = datetime.now(UTC)
    config = config or load_providers().get(PROVIDER_ID)
    scenes = scene.properties.get("scenes") or []
    if not scenes:
        raise ProviderParseError(config.provider_id, "scene evidence has no scenes")
    wanted = [*bands, *(["scl"] if mask_clouds and "scl" not in bands else [])]
    for s in scenes:
        for band in wanted:
            if band not in s["assets"]:
                raise ProviderParseError(config.provider_id, f"scene {s['id']} has no {band!r} band")
            check_href(s["assets"][band]["href"], config, allow_local=allow_local)

    arrays: dict[str, np.ndarray] = {}
    try:
        with _gdal_env(config):
            for band in wanted:
                merged = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
                for s in scenes:  # several tiles can cover one AOI: fill gaps tile by tile
                    asset = s["assets"][band]
                    raw = _read_asset(asset["href"], grid, 1, _resampling(band, asset, grid.res))
                    values = np.where(raw == 0, np.nan, raw)
                    if band != "scl":
                        scale, offset = _reflectance_scale(asset, s["boa_offset_applied"])
                        values = values * scale + offset
                    merged = np.where(np.isnan(merged), values, merged)
                arrays[band] = merged
    except rasterio.errors.RasterioIOError as exc:
        raise ProviderError(config.provider_id, f"could not read imagery: {exc}") from None

    valid = np.ones((grid.height, grid.width), dtype=bool)
    for band in bands:
        valid &= np.isfinite(arrays[band])
    if mask_clouds:
        valid &= np.isfinite(arrays["scl"]) & ~np.isin(np.nan_to_num(arrays["scl"]), list(bad_scl))
    for band in bands:
        arrays[band] = np.where(valid, arrays[band], np.nan).astype(np.float32)

    acquired = min(datetime.fromisoformat(s["acquired_at"].replace("Z", "+00:00")) for s in scenes)
    stack = BandStack(
        arrays={b: arrays[b] for b in [*bands, *(["scl"] if "scl" in arrays else [])]},
        valid=valid,
        grid=grid,
        scene_ids=[s["id"] for s in scenes],
        acquired_at=acquired.astimezone(UTC),
        offsets_applied={s["id"]: not s["boa_offset_applied"] for s in scenes},
    )
    if trace is not None:
        from inland_worker.data.trace import (
            ToolExecution,
        )  # local import: data depends on kit, not vice versa

        trace.record(
            ToolExecution(
                job_id=job_id,
                tool_name=f"imagery.read_bands:{config.provider_id}",
                input={
                    "scenes": stack.scene_ids,
                    "bands": list(bands),
                    "crs": grid.crs,
                    "res_m": grid.res,
                    "shape": [grid.height, grid.width],
                },
                output_summary={"valid_pct_inside": stack.valid_pct_inside},
                started_at=started,
                completed_at=datetime.now(UTC),
                status="ok",
            )
        )
    return stack


async def read_bands_async(*args: Any, **kwargs: Any) -> BandStack:
    """Same as read_bands, off the event loop (rasterio I/O is blocking)."""
    return await asyncio.to_thread(read_bands, *args, **kwargs)


def true_colour(
    scene: Evidence, grid: AoiGrid, *, config: ProviderConfig | None = None, allow_local: bool = False
) -> np.ndarray:
    """RGB uint8 array (3, H, W) from the `visual` asset, for thumbnails and overlays."""
    config = config or load_providers().get(PROVIDER_ID)
    out = np.zeros((3, grid.height, grid.width), dtype=np.uint8)
    with _gdal_env(config):
        for s in scene.properties["scenes"]:
            href = s["assets"]["visual"]["href"]
            check_href(href, config, allow_local=allow_local)
            tile = np.stack([_read_asset(href, grid, b, Resampling.average, np.uint8) for b in (1, 2, 3)])
            out = np.where(out == 0, tile, out)
    return out
