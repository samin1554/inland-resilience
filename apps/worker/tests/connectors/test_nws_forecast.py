import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from inland_worker.connectors.weather.nws_forecast import NwsForecastConnector
from inland_worker.kit import FixtureStore, HostNotAllowed, KitHttpClient, fetch
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.testing import ConnectorContract


class TestNwsForecast(ConnectorContract):
    connector_cls = NwsForecastConnector
    query_kwargs = {"bbox": (-117.2998, 34.0983, -117.2798, 34.1183)}

    def test_first_request_is_points_discovery(self):
        c = self.connector()
        (req,) = c.build_requests(self.query(c))
        assert req.path == "/points/34.1083,-117.2898" and req.label == "points"

    async def test_user_agent_header_is_sent(self):
        c = self.connector()
        recorded = FixtureStore().load(c.provider_id, "success")
        with respx.mock() as router:
            router.route().mock(side_effect=[httpx.Response(200, content=r.body) for r in recorded])
            await fetch(c, self.query(c), mode="live", client=KitHttpClient(c.config, env=self.fake_env(c)))
            ua = router.calls[0].request.headers["user-agent"]
        assert ua == self.fake_env(c)["NWS_USER_AGENT"]

    async def test_followed_link_to_other_host_is_refused(self):
        c = self.connector()
        points = {
            "properties": {
                "gridId": "X",
                "gridX": 1,
                "gridY": 1,
                "forecast": "https://evil.example.com/steal",
                "forecastHourly": "x",
            }
        }
        with respx.mock(assert_all_called=False) as router:
            evil = router.get(host="evil.example.com").mock(return_value=httpx.Response(200, json={}))
            router.route().mock(return_value=httpx.Response(200, json=points))
            with pytest.raises(HostNotAllowed):
                await fetch(
                    c, self.query(c), mode="live", client=KitHttpClient(c.config, env=self.fake_env(c))
                )
            assert not evil.called

    async def test_issue_time_is_observed_at_and_periods_kept(self):
        (item,) = (await self.run_fixture("success")).items
        assert item.properties["periods"] and item.properties["office"]
        assert item.observed_at < item.retrieved_at

    def test_old_forecast_is_flagged_stale(self):
        c = self.connector()
        q = self.query(c)
        now = datetime(2026, 9, 23, 12, tzinfo=UTC)
        pts = RawResponse(
            request=ProviderRequest(label="points"),
            url="u",
            status=200,
            retrieved_at=now,
            body=json.dumps({"properties": {"gridId": "SGX", "gridX": 1, "gridY": 2}}).encode(),
        )
        fc = {
            "properties": {
                "updateTime": "2026-09-22T00:00:00+00:00",
                "periods": [{"name": "Today", "temperature": 90}],
            }
        }
        fr = RawResponse(
            request=ProviderRequest(label="forecast", url="https://api.weather.gov/f"),
            url="u",
            status=200,
            retrieved_at=now,
            body=json.dumps(fc).encode(),
        )
        (item,) = c.parse([pts, fr], q)
        assert "stale_forecast" in item.quality_flags
