import json
from datetime import UTC, datetime

from inland_worker.kit import arcgis
from inland_worker.kit.redact import Redactor


def test_esri_rings_to_polygon_with_hole():
    outer = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]  # clockwise
    hole = [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]  # counter-clockwise
    gj = arcgis.esri_to_geojson({"rings": [outer, hole]})
    assert gj == {"type": "Polygon", "coordinates": [outer, hole]}


def test_esri_two_outer_rings_to_multipolygon():
    a = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    b = [[5, 5], [5, 6], [6, 6], [6, 5], [5, 5]]
    assert arcgis.esri_to_geojson({"rings": [a, b]})["type"] == "MultiPolygon"


def test_esri_point_and_none():
    assert arcgis.esri_to_geojson({"x": -117.1, "y": 34.2}) == {
        "type": "Point",
        "coordinates": [-117.1, 34.2],
    }
    assert arcgis.esri_to_geojson(None) is None


def test_epoch_ms():
    assert arcgis.epoch_ms(1790221559000) == datetime(2026, 9, 24, 3, 45, 59, tzinfo=UTC)
    assert arcgis.epoch_ms(None) is None


def test_exceeded_flag_in_both_formats():
    assert arcgis.exceeded_transfer_limit({"exceededTransferLimit": True})
    assert arcgis.exceeded_transfer_limit({"properties": {"exceededTransferLimit": True}})
    assert not arcgis.exceeded_transfer_limit({"features": []})


def test_redactor_masks_plain_and_url_encoded():
    r = Redactor(["a b/c+secret"])
    assert "secret" not in r.text("x=a+b%2Fc%2Bsecret and a b/c+secret")
    assert Redactor([None, "", "abc"]).text("abc") == "abc"  # too short to mask safely
    assert r.bytes(json.dumps({"k": "a b/c+secret"}).encode()).count(b"***") == 1
