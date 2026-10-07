"""The supported region (ADR-012): the committed US outline, county names, and the seed generated from them."""

import importlib.util
import json
from pathlib import Path

from shapely.geometry import Point, shape

from inland_worker.agent.guardrails import REGION_FILE, region

WORKER = Path(__file__).resolve().parents[1]
INSIDE = {
    "Sacramento": (-121.49, 38.58),
    "Denver": (-104.99, 39.74),
    "Anchorage": (-149.9, 61.22),
    "Honolulu": (-157.86, 21.31),
    "Miami": (-80.19, 25.76),
    "Washington DC": (-77.04, 38.9),
}
OUTSIDE = {
    "Tijuana": (-117.02, 32.51),
    "Vancouver": (-123.12, 49.28),
    "Gulf of Mexico": (-90.0, 26.0),
    "San Juan PR (territories out of scope)": (-66.1, 18.47),
}


def test_outline_is_the_50_states_and_dc():
    geom = region()
    assert geom.is_valid and geom.geom_type == "MultiPolygon"
    for name, pt in INSIDE.items():
        assert geom.contains(Point(pt)), name
    for name, pt in OUTSIDE.items():
        assert not geom.contains(Point(pt)), name
    props = json.loads(REGION_FILE.read_text())["features"][0]["properties"]
    assert len(props["states"]) == 51 and "DC" in props["states"] and "PR" not in props["states"]
    assert len(REGION_FILE.read_bytes()) < 1_000_000


def test_counties_name_places():
    fc = json.loads((REGION_FILE.parent / "us_counties.geojson").read_text())
    assert len(fc["features"]) > 3100
    denver = [f for f in fc["features"] if shape(f["geometry"]).contains(Point(INSIDE["Denver"]))]
    assert [(f["properties"]["name"], f["properties"]["state"]) for f in denver] == [("Denver County", "CO")]


def test_seed_sql_is_idempotent_and_matches_the_outline():
    spec = importlib.util.spec_from_file_location("brs", WORKER / "scripts" / "build_region_seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    outline = json.loads(REGION_FILE.read_text())
    sql = mod.seed_sql(outline)
    assert "ON CONFLICT (id) DO UPDATE" in sql and "'region'" in sql
    seeded = json.loads(sql.split("ST_GeomFromGeoJSON('")[1].split("')")[0])
    assert shape(seeded).equals(shape(outline["features"][0]["geometry"]))
