from datetime import UTC, datetime

import pytest

from inland_worker.connectors.fire.firms import FirmsConnector
from inland_worker.kit import ProviderParseError
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.testing import ConnectorContract


class TestFirms(ConnectorContract):
    connector_cls = FirmsConnector
    query_kwargs = {"bbox": (-117.8, 33.8, -114.1, 35.9), "params": {"source": "VIIRS_NOAA21_NRT", "days": 2}}

    def test_request_uses_key_placeholder_and_bbox(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.path == "/{MAP_KEY}/VIIRS_NOAA21_NRT/-117.8000,33.8000,-114.1000,35.9000/2"

    def test_days_outside_1_to_5_rejected_before_any_call(self):
        c = self.connector()
        with pytest.raises(ValueError):
            c.query(bbox=(-117.8, 33.8, -114.1, 35.9), params={"days": 6})

    async def test_time_and_confidence_mapping(self):
        items = (await self.run_fixture("success")).items
        first = items[0]
        assert first.observed_at == datetime(2026, 9, 22, 9, 48, tzinfo=UTC)
        assert first.geometry.coordinates == [-117.12004, 34.18612]  # [lon, lat]
        assert first.properties["confidence"] == "nominal"
        assert first.properties["confidence_scheme"] == "viirs_category"
        low = items[2]
        assert "low_confidence" in low.quality_flags and "missing_frp" in low.quality_flags

    def test_invalid_key_text_is_a_parse_error(self):
        c = self.connector()
        resp = RawResponse(
            request=ProviderRequest(),
            url="x",
            status=200,
            body=b"Invalid MAP_KEY.",
            retrieved_at=datetime.now(UTC),
        )
        with pytest.raises(ProviderParseError):
            c.parse([resp], self.query(c))
