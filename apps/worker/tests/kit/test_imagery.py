"""kit/imagery.py on synthetic GeoTIFFs with known values: exact, offline checks of the four lessons."""

from datetime import UTC, datetime

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box, mapping

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.data import MemoryTraceSink
from inland_worker.kit import HostNotAllowed, load_providers
from inland_worker.kit.imagery import aoi_grid, check_href, pick_scene, read_bands, repair, utm_crs_for

AOI = mapping(box(-117.100, 34.100, -117.090, 34.110))  # ~920 m x 1110 m near San Bernardino
UTM_ORIGIN = (
    489_000,
    3_776_000,
)  # upper-left, EPSG:32611; 4 km square covers the AOI (x 490.8-491.7 km, y 3773.2-3774.4 km)


def write_tif(path, value, res, size, *, origin=UTM_ORIGIN, dtype="uint16", patch=None):
    data = np.full((size, size), value, dtype=dtype)
    if patch is not None:  # (row_slice, col_slice, value)
        rows, cols, v = patch
        data[rows, cols] = v
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=size,
        height=size,
        count=1,
        dtype=dtype,
        crs="EPSG:32611",
        transform=from_origin(origin[0], origin[1], res, res),
        nodata=0,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def scene(
    tmp_path,
    *,
    offset_applied,
    nir=3000,
    swir=2000,
    cloud_quadrant=False,
    name="A",
    origin=UTM_ORIGIN,
    size_m=4000,
):
    d = tmp_path / name
    d.mkdir()
    patch = (slice(0, size_m // 40), slice(0, size_m // 40), 9) if cloud_quadrant else None
    assets = {
        "nir": {
            "href": write_tif(d / "nir.tif", nir, 10, size_m // 10, origin=origin),
            "scale": 1e-4,
            "offset": -0.1,
            "spatial_resolution": 10,
        },
        "swir22": {
            "href": write_tif(d / "swir.tif", swir, 20, size_m // 20, origin=origin),
            "scale": 1e-4,
            "offset": -0.1,
            "spatial_resolution": 20,
        },
        "scl": {
            "href": write_tif(d / "scl.tif", 4, 20, size_m // 20, origin=origin, dtype="uint8", patch=patch),
            "spatial_resolution": 20,
        },
    }
    return {
        "id": f"S2X_11SMT_20241019_0_{name}",
        "acquired_at": "2024-10-19T18:35:00Z",
        "boa_offset_applied": offset_applied,
        "assets": assets,
    }


def scene_evidence(*scenes, coverage=1.0, cloud=1.5, date="2024-10-19"):
    return Evidence(
        id=f"e-{date}-{cloud}",
        evidence_type=EvidenceType.SATELLITE_MEASUREMENT,
        source="test",
        observed_at=datetime(2024, 10, 19, tzinfo=UTC),
        retrieved_at=datetime(2024, 10, 20, tzinfo=UTC),
        geometry=None,
        properties={
            "date": date,
            "aoi_coverage": coverage,
            "scene_cloud_max_pct": cloud,
            "scenes": list(scenes),
        },
        quality_flags=[],
        limitations=["x"],
        source_url="https://example.com",
    )


# --- lesson 1: the offset rule -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("offset_applied", "expected_nir", "expected_swir"), [(False, 0.2, 0.1), (True, 0.3, 0.2)]
)
def test_offset_only_when_not_already_applied(tmp_path, offset_applied, expected_nir, expected_swir):
    grid = aoi_grid(AOI)
    stack = read_bands(scene_evidence(scene(tmp_path, offset_applied=offset_applied)), grid, allow_local=True)
    inside = grid.inside
    assert np.allclose(stack.arrays["nir"][inside], expected_nir, atol=1e-6)
    assert np.allclose(stack.arrays["swir22"][inside], expected_swir, atol=1e-6)


# --- cloud masking -----------------------------------------------------------------------------------------
def test_cloudy_scl_pixels_are_nan_in_every_band(tmp_path):
    grid = aoi_grid(AOI)
    stack = read_bands(
        scene_evidence(scene(tmp_path, offset_applied=True, cloud_quadrant=True)), grid, allow_local=True
    )
    cloudy = stack.arrays["scl"] == 9
    assert cloudy.any() and (~cloudy & grid.inside).any()
    assert np.isnan(stack.arrays["nir"][cloudy]).all() and np.isnan(stack.arrays["swir22"][cloudy]).all()
    assert 0 < stack.valid_pct_inside < 100


def test_no_masking_when_asked(tmp_path):
    grid = aoi_grid(AOI)
    stack = read_bands(
        scene_evidence(scene(tmp_path, offset_applied=True, cloud_quadrant=True)),
        grid,
        mask_clouds=False,
        allow_local=True,
    )
    assert stack.valid_pct_inside == 100 and "scl" not in stack.arrays


# --- several tiles cover one AOI ---------------------------------------------------------------------------
def test_second_tile_fills_gaps_of_the_first(tmp_path):
    grid = aoi_grid(AOI)
    # tile A covers only a 500 m square at the grid's top-left; tile B covers everything with a different value
    west = scene(
        tmp_path,
        offset_applied=True,
        nir=3000,
        name="A",
        origin=(grid.transform.c, grid.transform.f),
        size_m=500,
    )
    full = scene(tmp_path, offset_applied=True, nir=5000, name="B")
    stack = read_bands(scene_evidence(west, full), grid, allow_local=True)
    nir, rows_a = stack.arrays["nir"], 500 // 20  # tile A is a 500 m square at the grid's top-left corner
    assert np.isclose(nir[: rows_a - 1, : rows_a - 1], 0.3).all()  # inside tile A: tile A's value
    assert np.isclose(nir[rows_a + 1 :, 0], 0.5).all()  # below tile A: gap filled by tile B
    assert np.isclose(nir[:, -1], 0.5).all()  # east edge: tile B
    assert stack.scene_ids == [west["id"], full["id"]]


# --- lesson 3 + grid ---------------------------------------------------------------------------------------
def test_invalid_bowtie_aoi_is_repaired():
    bowtie = Polygon(
        [(-117.10, 34.10), (-117.09, 34.11), (-117.09, 34.10), (-117.10, 34.11), (-117.10, 34.10)]
    )
    assert not bowtie.is_valid
    fixed = repair(bowtie)
    assert fixed.is_valid and fixed.area > 0
    assert aoi_grid(bowtie).inside.any()


@pytest.mark.parametrize(
    ("lon", "lat", "epsg"),
    [(-117.1, 34.1, "EPSG:32611"), (151.2, -33.9, "EPSG:32756"), (2.35, 48.85, "EPSG:32631")],
)
def test_utm_zone_from_centroid(lon, lat, epsg):
    assert utm_crs_for(box(lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01)) == epsg


def test_grid_inside_mask_matches_area():
    grid = aoi_grid(AOI, res=20)
    expected = 920 * 1110 / 400  # ~ m2 / pixel area
    assert abs(grid.inside.sum() - expected) / expected < 0.05


# --- safety ------------------------------------------------------------------------------------------------
def test_only_allowlisted_https_image_urls():
    cfg = load_providers().get("earth_search_s2")
    check_href("https://sentinel-cogs.s3.us-west-2.amazonaws.com/x/B08.tif", cfg)
    for bad in (
        "http://sentinel-cogs.s3.us-west-2.amazonaws.com/x.tif",
        "https://evil.example.com/x.tif",
        "s3://sentinel-cogs/x.tif",
        "/etc/passwd",
    ):
        with pytest.raises(HostNotAllowed):
            check_href(bad, cfg)


def test_read_refuses_non_allowlisted_scene_before_any_io(tmp_path):
    s = scene(tmp_path, offset_applied=True)
    s["assets"]["nir"]["href"] = "https://evil.example.com/B08.tif"
    with pytest.raises(HostNotAllowed):
        read_bands(scene_evidence(s), aoi_grid(AOI))


# --- choosing a date, tracing ------------------------------------------------------------------------------
def test_pick_scene_prefers_full_coverage_then_least_cloud():
    a = scene_evidence(coverage=1.0, cloud=7.5, date="2024-10-09")
    b = scene_evidence(coverage=1.0, cloud=1.5, date="2024-10-19")
    c = scene_evidence(coverage=0.25, cloud=0.1, date="2024-10-31")  # least cloudy, but only clips the AOI
    assert pick_scene([a, b, c]) is b
    assert pick_scene([c]) is None


def test_read_is_traced(tmp_path):
    sink = MemoryTraceSink()
    read_bands(
        scene_evidence(scene(tmp_path, offset_applied=True)),
        aoi_grid(AOI),
        allow_local=True,
        trace=sink,
        job_id="analysis_1",
    )
    (rec,) = sink.records
    assert rec.tool_name == "imagery.read_bands:earth_search_s2" and rec.job_id == "analysis_1"
    assert rec.output_summary["valid_pct_inside"] == 100
