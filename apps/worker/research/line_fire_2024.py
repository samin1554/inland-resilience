"""Proof of concept (ADR-009): 2024 Line Fire burn severity from Sentinel-2, compared with the official BAER map.

    make demo-line-fire            # in Docker, writes to docs/research/line-fire-2024/output/
    uv run --group research python research/line_fire_2024.py --out /tmp/line-fire

Research code, not production: kit/imagery.py will turn these steps into the reusable STAC-imagery pattern.
Needs no account or key. Contains modified Copernicus Sentinel data 2024.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
import matplotlib
import numpy as np
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

CALFIRE = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/California_Historic_Fire_Perimeters/FeatureServer/2/query"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
BAER = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_BAER_SoilBurnSeverityClassification/ImageServer/exportImage"
BEFORE, AFTER = (
    "2024-08-20",
    "2024-10-19",
)  # least-cloudy full-coverage dates around the fire (Sep 5 - late Sep 2024)
DST_CRS, RES = "EPSG:32611", 20.0  # UTM 11N, 20 m (the SWIR/SCL resolution)
BAD_SCL = [0, 1, 3, 8, 9, 10]  # no data, saturated, cloud shadow, cloud medium/high, thin cirrus
EDGES = [0.10, 0.27, 0.66]  # USGS / Key & Benson (2006) dNBR thresholds collapsed to BAER's 4 classes
NAMES = ["Unburned/very low", "Low", "Moderate", "High"]


def fire_perimeter(http: httpx.Client):
    params = {
        "where": "FIRE_NAME='LINE' AND YEAR_=2024",
        "outFields": "FIRE_NAME,GIS_ACRES",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    feature = http.get(CALFIRE, params=params).raise_for_status().json()["features"][0]
    # lesson 3: CAL FIRE perimeters can be invalid geometries; repair before use
    return make_valid(shape(feature["geometry"])), feature["properties"]["GIS_ACRES"]


class Grid:
    def __init__(self, fire_ll):
        self.fire_ll = fire_ll
        self.fire = shp_transform(
            Transformer.from_crs("EPSG:4326", DST_CRS, always_xy=True).transform, fire_ll
        )
        self.minx, self.miny, self.maxx, self.maxy = self.fire.buffer(600).bounds
        self.w, self.h = int((self.maxx - self.minx) // RES), int((self.maxy - self.miny) // RES)
        self.transform = from_origin(self.minx, self.maxy, RES, RES)
        self.inside = ~geometry_mask(
            [mapping(self.fire)], out_shape=(self.h, self.w), transform=self.transform
        )

    def warp(self, src, band, dst, resampling):
        reproject(
            rasterio.band(src, band),
            dst,
            dst_transform=self.transform,
            dst_crs=DST_CRS,
            resampling=resampling,
            src_nodata=0,
            dst_nodata=0,
        )


def scenes(catalog: Client, grid: Grid, date: str):
    items = catalog.search(collections=["sentinel-2-l2a"], bbox=grid.fire_ll.bounds, datetime=date).items()
    # lesson 2: a tile/date can have several processing versions; keep one (version 0) per tile
    return [i for i in items if i.id.endswith("_0_L2A")]


def reflectance(items, asset: str, grid: Grid, resampling) -> np.ndarray:
    out = np.full((grid.h, grid.w), np.nan, dtype=np.float32)
    for it in items:
        tmp = np.zeros((grid.h, grid.w), dtype=np.float32)
        with rasterio.open(it.assets[asset].href) as src:  # lesson: windowed reads only, never whole scenes
            grid.warp(src, 1, tmp, resampling)
        tmp = np.where(tmp == 0, np.nan, tmp)
        if asset != "scl":
            rb = it.assets[asset].extra_fields["raster:bands"][0]
            # lesson 1: apply the BOA offset only if Earth Search has NOT already applied it (check per item)
            offset = 0.0 if it.properties.get("earthsearch:boa_offset_applied") else rb["offset"]
            tmp = tmp * rb["scale"] + offset
        out = np.where(np.isnan(out), tmp, out)
    return out


def true_colour(items, grid: Grid) -> np.ndarray:
    out = np.zeros((3, grid.h, grid.w), dtype=np.uint8)
    for it in items:
        tmp = np.zeros((3, grid.h, grid.w), dtype=np.uint8)
        with rasterio.open(it.assets["visual"].href) as src:
            for b in range(3):
                grid.warp(src, b + 1, tmp[b], Resampling.average)
        out = np.where(out == 0, tmp, out)
    return out


def nbr(catalog: Client, grid: Grid, date: str):
    items = scenes(catalog, grid, date)
    nir = reflectance(items, "nir", grid, Resampling.average)
    swir = reflectance(items, "swir22", grid, Resampling.bilinear)
    scl = reflectance(items, "scl", grid, Resampling.nearest)
    valid = np.isfinite(nir) & np.isfinite(swir) & ~np.isin(np.nan_to_num(scl), BAD_SCL) & (nir + swir > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (
            np.where(valid, (nir - swir) / (nir + swir), np.nan),
            [i.id for i in items],
            true_colour(items, grid),
        )


def baer_classes(http: httpx.Client, grid: Grid, out: Path) -> np.ndarray:
    params = {
        "bbox": f"{grid.minx},{grid.miny},{grid.maxx},{grid.maxy}",
        "bboxSR": 32611,
        "imageSR": 32611,
        "size": f"{grid.w},{grid.h}",
        "format": "tiff",
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "mosaicRule": json.dumps(
            {"mosaicMethod": "esriMosaicAttribute", "where": "beginyear<=2024 AND endyear>=2024"}
        ),
        "f": "image",
    }
    path = out / "baer.tif"
    path.write_bytes(http.get(BAER, params=params).raise_for_status().content)
    with rasterio.open(path) as src:
        values = src.read(1)
    return np.where((values >= 1) & (values <= 4), values, 0)  # 1..4 = NAMES, 5 = masked (developed)


def figure(r: dict, grid: Grid, ours, baer, rgb_pre, rgb_post, path: Path) -> None:
    def day(scene_id: str) -> str:
        return datetime.strptime(scene_id.split("_")[2], "%Y%m%d").strftime("%b %d, %Y")

    def stretch(x):
        x = np.moveaxis(x, 0, -1).astype(float)
        lo, hi = np.percentile(x[x > 0], [2, 98])
        return np.clip((x - lo) / (hi - lo), 0, 1)

    cols = ["#ffffff00", "#1a9850", "#fee08b", "#fc8d59", "#b2182b"]
    cmap, inside = ListedColormap(cols), grid.inside
    pw = 0.235
    ph = pw * 15 / 7.2 * grid.h / grid.w
    fig = plt.figure(figsize=(15, 7.2), facecolor="#f5f5f5")
    fig.text(
        0.02,
        0.955,
        "Line Fire (2024), San Bernardino NF: our Sentinel-2 burn severity vs the official USFS BAER map",
        fontsize=14,
        color="#2d3142",
    )
    fig.text(
        0.02,
        0.915,
        f"Sentinel-2 L2A via Earth Search (no account)  ·  before {day(r['scenes_before'][0])}  ·  "
        f"after {day(r['scenes_after'][0])}  ·  {r['valid_pixel_pct_inside']:.0f}% cloud-free inside the fire  ·  "
        f"computed in {r['seconds']} s  ·  Contains modified Copernicus Sentinel data 2024",
        fontsize=9,
        color="#4f5d75",
    )
    top = 0.86
    panels = [
        (f"Before: {day(r['scenes_before'][0])}", stretch(rgb_pre), None),
        (f"After: {day(r['scenes_after'][0])}", stretch(rgb_post), None),
        ("Ours: dNBR severity (computed)", np.where(inside, ours, 0), cmap),
        ("Official: USFS BAER soil burn severity", np.where(inside, baer, 0), cmap),
    ]
    for k, (title, img, cm) in enumerate(panels):
        ax = fig.add_axes([0.02 + k * 0.245, top - ph, pw, ph])
        ax.set_facecolor("#e8e8e8")
        if cm:
            ax.imshow(img, cmap=cm, vmin=0, vmax=4, interpolation="nearest")
        else:
            ax.imshow(img)
        ax.contour(inside, levels=[0.5], colors="k", linewidths=0.6)
        ax.set_title(title, fontsize=10.5, color="#2d3142", loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    yb = top - ph - 0.055
    fig.legend(
        handles=[Patch(color=c, label=n) for c, n in zip(cols[1:], NAMES, strict=True)]
        + [Patch(facecolor="none", edgecolor="k", label="CAL FIRE perimeter")],
        loc="upper left",
        bbox_to_anchor=(0.51, yb + 0.03),
        ncol=5,
        frameon=False,
        fontsize=9,
    )
    ax = fig.add_axes([0.06, 0.07, 0.42, yb - 0.12])
    x, w = np.arange(4), 0.38
    ax.bar(
        x - w / 2, [r["ours_acres"][n] for n in NAMES], w, color="#eb6c36", label="Ours (dNBR, Sentinel-2)"
    )
    ax.bar(x + w / 2, [r["baer_acres"][n] for n in NAMES], w, color="#4f5d75", label="Official (BAER)")
    ax.set_xticks(x, NAMES, fontsize=9)
    ax.set_ylabel("acres", fontsize=9)
    ax.legend(frameon=False, fontsize=9)
    ax.set_title(
        "Acres by severity class inside the fire perimeter", fontsize=10.5, loc="left", color="#2d3142"
    )
    fig.text(
        0.55,
        yb - 0.04,
        f"Exact class agreement: {r['exact_class_agreement_pct']}%\nWithin one class:      {r['within_one_class_pct']}%\n"
        f"dNBR median: {r['dnbr_inside_p25_median_p75'][1]} inside the fire, {r['dnbr_outside_median']} outside\n"
        f"Fire area: {r['perimeter_acres_grid']:,} acres on our 20 m grid (CAL FIRE {r['perimeter_acres_calfire']:,.0f})\n\n"
        "Why ours reads higher: dNBR measures vegetation loss;\nBAER measures soil damage, usually lower in chaparral.\n"
        "Standard forest thresholds used; calibrating for chaparral\nis an S6/S8 task.",
        fontsize=10.5,
        va="top",
        color="#2d3142",
        family="monospace",
    )
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="out", help="output folder (created if missing)")
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    headers = {"User-Agent": "inland-resilience-agent/0.1 (+https://github.com/samin1554/inland-resilience)"}
    with (
        httpx.Client(timeout=120, headers=headers, follow_redirects=True) as http,
        rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            AWS_NO_SIGN_REQUEST="YES",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            GDAL_HTTP_MULTIRANGE="YES",
            VSI_CACHE="TRUE",
        ),
    ):
        print("1/4 Line Fire perimeter (CAL FIRE)…")
        fire_ll, calfire_acres = fire_perimeter(http)
        grid = Grid(fire_ll)
        catalog = Client.open(EARTH_SEARCH)
        print(f"2/4 Sentinel-2 before ({BEFORE}) and after ({AFTER})…")
        nbr_pre, ids_pre, rgb_pre = nbr(catalog, grid, BEFORE)
        nbr_post, ids_post, rgb_post = nbr(catalog, grid, AFTER)
        dnbr = nbr_pre - nbr_post
        ours = np.where(np.isnan(dnbr), 0, np.digitize(dnbr, EDGES) + 1)
        print("3/4 official BAER soil burn severity…")
        baer = baer_classes(http, grid, out)

    inside = grid.inside
    px_acres = RES * RES / 4046.8564224
    m_ours, m_both = inside & (ours > 0), inside & (ours > 0) & (baer > 0)
    r = {
        "fire": "LINE 2024 (CAL FIRE California_Historic_Fire_Perimeters)",
        "perimeter_acres_calfire": calfire_acres,
        "perimeter_acres_grid": round(inside.sum() * px_acres),
        "scenes_before": ids_pre,
        "scenes_after": ids_post,
        "valid_pixel_pct_inside": round(100 * m_ours.sum() / inside.sum(), 1),
        "dnbr_inside_p25_median_p75": [
            round(float(v), 3) for v in np.nanpercentile(np.where(inside, dnbr, np.nan), [25, 50, 75])
        ],
        "dnbr_outside_median": round(float(np.nanmedian(np.where(~inside, dnbr, np.nan))), 3),
        "offset_rule": "offset applied only where earthsearch:boa_offset_applied is false",
        "ours_acres": {n: round(((ours == i + 1) & inside).sum() * px_acres) for i, n in enumerate(NAMES)},
        "baer_acres": {n: round(((baer == i + 1) & inside).sum() * px_acres) for i, n in enumerate(NAMES)},
        "baer_coverage_pct_inside": round(100 * (inside & (baer > 0)).sum() / inside.sum(), 1),
        "exact_class_agreement_pct": round(100 * ((ours == baer) & m_both).sum() / max(m_both.sum(), 1), 1),
        "within_one_class_pct": round(
            100 * ((np.abs(ours.astype(int) - baer.astype(int)) <= 1) & m_both).sum() / max(m_both.sum(), 1),
            1,
        ),
        "seconds": round(time.time() - t0, 1),
    }
    print("4/4 figure…")
    (out / "results.json").write_text(json.dumps(r, indent=2) + "\n")
    figure(r, grid, ours, baer, rgb_pre, rgb_post, out / "line-fire-2024-dnbr-vs-baer.png")
    print(json.dumps({k: r[k] for k in ("exact_class_agreement_pct", "within_one_class_pct", "seconds")}))
    print(f"wrote {out}/results.json and {out}/line-fire-2024-dnbr-vs-baer.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
