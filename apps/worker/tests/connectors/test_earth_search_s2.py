import json
from datetime import UTC, datetime

import pytest

from inland_worker.connectors.imagery.earth_search_s2 import EarthSearchS2Connector
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.testing import ConnectorContract

LINE_FIRE_BBOX = (-117.185, 34.092, -116.94, 34.218)


def feature(item_id, date, tile, cloud, lon0=-117.3, lat0=34.0, size=0.5, offset_applied=True):
    return {
        "id": item_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon0, lat0],
                    [lon0 + size, lat0],
                    [lon0 + size, lat0 + size],
                    [lon0, lat0 + size],
                    [lon0, lat0],
                ]
            ],
        },
        "properties": {
            "datetime": f"{date}T18:40:00Z",
            "grid:code": tile,
            "eo:cloud_cover": cloud,
            "earthsearch:boa_offset_applied": offset_applied,
            "platform": "sentinel-2a",
        },
        "assets": {
            b: {
                "href": f"https://sentinel-cogs.s3.us-west-2.amazonaws.com/{item_id}/{b}.tif",
                "raster:bands": [{"scale": 0.0001, "offset": -0.1, "nodata": 0}],
            }
            for b in ("red", "nir", "swir22", "scl", "visual")
        },
    }


class TestEarthSearchS2(ConnectorContract):
    connector_cls = EarthSearchS2Connector
    query_kwargs = {
        "bbox": LINE_FIRE_BBOX,
        "date_range": {"start": "2024-10-01", "end": "2024-10-31"},
        "params": {"page_size": 10, "cloud_limit": 100},
    }

    def parse_features(self, *features):
        c = self.connector()
        body = json.dumps({"features": list(features), "links": []}).encode()
        resp = RawResponse(
            request=ProviderRequest(label="search"),
            url="u",
            status=200,
            body=body,
            retrieved_at=datetime(2024, 11, 1, tzinfo=UTC),
        )
        return c.parse([resp], self.query(c))

    def test_search_is_a_post_with_window_bbox_and_cloud_filter(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.method == "POST" and req.path == "/search"
        assert req.json_body["collections"] == ["sentinel-2-l2a"]
        assert req.json_body["datetime"] == "2024-10-01T00:00:00Z/2024-10-31T23:59:59Z"
        assert req.json_body["query"] == {"eo:cloud_cover": {"lte": 100}}

    def test_date_range_is_required(self):
        c = self.connector()
        with pytest.raises(ValueError, match="date_range"):
            c.build_requests(c.query(bbox=LINE_FIRE_BBOX))

    def test_one_scene_per_tile_per_date_least_cloudy_wins(self):
        (ev,) = self.parse_features(
            feature("S2C_11SMT_20241031_1_L2A", "2024-10-31", "MGRS-11SMT", cloud=0.07),
            feature("S2A_11SMT_20241031_0_L2A", "2024-10-31", "MGRS-11SMT", cloud=3.0),
        )
        assert [s["id"] for s in ev.properties["scenes"]] == ["S2C_11SMT_20241031_1_L2A"]

    def test_offset_flag_and_scales_are_kept_per_scene(self):
        (ev,) = self.parse_features(feature("S2A_X_1", "2024-10-19", "T1", 1.0, offset_applied=False))
        (s,) = ev.properties["scenes"]
        assert s["boa_offset_applied"] is False
        assert s["assets"]["nir"]["scale"] == 0.0001 and s["assets"]["nir"]["offset"] == -0.1

    def test_partial_coverage_is_flagged(self):
        (ev,) = self.parse_features(feature("S2A_X_1", "2024-10-19", "T1", 1.0, lon0=-117.0, size=0.05))
        assert ev.properties["aoi_coverage"] < 0.99 and "partial_aoi_coverage" in ev.quality_flags

    def test_follow_resends_the_next_link_body(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        page = {
            "features": [],
            "links": [
                {
                    "rel": "next",
                    "method": "POST",
                    "href": "https://earth-search.aws.element84.com/v1/search",
                    "body": {**req.json_body, "next": "tok123"},
                }
            ],
        }
        resp = RawResponse(
            request=req, url="u", status=200, body=json.dumps(page).encode(), retrieved_at=datetime.now(UTC)
        )
        (nxt,) = c.follow(resp, self.query(c))
        assert nxt.method == "POST" and nxt.json_body["next"] == "tok123" and nxt.label == "page_2"

    async def test_recorded_october_2024_has_expected_dates(self):
        items = (await self.run_fixture("success")).items
        dates = [e.properties["date"] for e in items]
        assert "2024-10-19" in dates and dates == sorted(dates)
        oct19 = next(e for e in items if e.properties["date"] == "2024-10-19")
        assert oct19.properties["aoi_coverage"] == 1.0 and len(oct19.properties["scenes"]) == 2
