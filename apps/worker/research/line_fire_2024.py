"""Proof of concept (ADR-009): 2024 Line Fire burn severity from Sentinel-2, compared with the official BAER map.

    make demo-line-fire            # in Docker, writes to docs/research/line-fire-2024/output/
    uv run --group research python research/line_fire_2024.py --out /tmp/line-fire

Uses the worker's real pipeline: the `earth_search_s2` connector finds scenes and `kit/imagery.py` reads them.
Needs no account or key. Contains modified Copernicus Sentinel data 2024.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
import matplotlib
import numpy as np
import rasterio
from shapely.geometry import mapping

from inland_worker.connectors.registry import get_connector
from inland_worker.kit import fetch
from inland_worker.kit.imagery import AoiGrid, aoi_grid, pick_scene, read_bands, repair, true_colour

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

CALFIRE = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/California_Historic_Fire_Perimeters/FeatureServer/2/query"
BAER = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_BAER_SoilBurnSeverityClassification/ImageServer/exportImage"
BEFORE, AFTER = (
    "2024-08-20",
    "2024-10-19",
)  # least-cloudy full-coverage dates around the fire (Sep 5 - late Sep 2024)
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
    return repair(feature["geometry"]), feature["properties"]["GIS_ACRES"]  # kit repairs invalid perimeters


def scene_on(day: str, fire_ll):
    """Scene discovery through the real connector (allowlisted HTTP, paging, one scene per tile)."""
    connector = get_connector("earth_search_s2")
    query = connector.query(
        area=mapping(fire_ll), date_range={"start": day, "end": day}, params={"cloud_limit": 100}
    )
    return pick_scene(asyncio.run(fetch(connector, query, mode="live")).items)


def nbr(scene, grid: AoiGrid):
    stack = read_bands(scene, grid, bands=("nir", "swir22"))  # offset rule + SCL mask live in the kit
    nir, swir = stack.arrays["nir"], stack.arrays["swir22"]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(nir + swir > 0, (nir - swir) / (nir + swir), np.nan), stack.scene_ids


def baer_classes(http: httpx.Client, grid: AoiGrid, out: Path) -> np.ndarray:
    minx, maxy = grid.transform.c, grid.transform.f  # grid origin (upper-left) in its UTM CRS
    maxx, miny = minx + grid.width * grid.res, maxy - grid.height * grid.res
    epsg = int(grid.crs.split(":")[1])
    params = {
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "bboxSR": epsg,
        "imageSR": epsg,
        "size": f"{grid.width},{grid.height}",
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


def figure(r: dict, grid: AoiGrid, ours, baer, rgb_pre, rgb_post, path: Path) -> None:
    def day(scene_id: str) -> str:
        return datetime.strptime(scene_id.split("_")[2], "%Y%m%d").strftime("%b %d, %Y")

    def stretch(x):
        x = np.moveaxis(x, 0, -1).astype(float)
        lo, hi = np.percentile(x[x > 0], [2, 98])
        return np.clip((x - lo) / (hi - lo), 0, 1)

    cols = ["#ffffff00", "#1a9850", "#fee08b", "#fc8d59", "#b2182b"]
    cmap, inside = ListedColormap(cols), grid.inside
    pw = 0.235
    ph = pw * 15 / 7.2 * grid.height / grid.width
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
    with httpx.Client(timeout=120, headers=headers, follow_redirects=True) as http:
        print("1/4 Line Fire perimeter (CAL FIRE)…")
        fire_ll, calfire_acres = fire_perimeter(http)
        grid = aoi_grid(fire_ll, res=20.0, buffer_m=600)
        print(f"2/4 Sentinel-2 before ({BEFORE}) and after ({AFTER}) via earth_search_s2 + kit/imagery…")
        pre_scene, post_scene = scene_on(BEFORE, fire_ll), scene_on(AFTER, fire_ll)
        nbr_pre, ids_pre = nbr(pre_scene, grid)
        nbr_post, ids_post = nbr(post_scene, grid)
        rgb_pre, rgb_post = true_colour(pre_scene, grid), true_colour(post_scene, grid)
        dnbr = nbr_pre - nbr_post
        ours = np.where(np.isnan(dnbr), 0, np.digitize(dnbr, EDGES) + 1)
        print("3/4 official BAER soil burn severity…")
        baer = baer_classes(http, grid, out)

    inside = grid.inside
    px_acres = grid.pixel_area_m2 / 4046.8564224
    m_ours, m_both = inside & (ours > 0), inside & (ours > 0) & (baer > 0)
    r = {
        "fire": "LINE 2024 (CAL FIRE California_Historic_Fire_Perimeters)",
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": [grid.height, grid.width]},
        "perimeter_acres_calfire": calfire_acres,
        "perimeter_acres_grid": round(inside.sum() * px_acres),
        "scenes_before": ids_pre,
        "scenes_after": ids_post,
        "valid_pixel_pct_inside": round(100 * m_ours.sum() / inside.sum(), 1),
        "dnbr_inside_p25_median_p75": [
            round(float(v), 3) for v in np.nanpercentile(np.where(inside, dnbr, np.nan), [25, 50, 75])
        ],
        "dnbr_outside_median": round(float(np.nanmedian(np.where(~inside, dnbr, np.nan))), 3),
        "pipeline": "earth_search_s2 connector + kit/imagery.read_bands",
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
