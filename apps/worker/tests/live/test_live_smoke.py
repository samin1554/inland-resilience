"""Real calls to real providers. Not part of the normal test run.

    make test-live        (reads keys from the repo's .env)

Each test proves the full live path works today: allowlisted HTTP → parse → schema-valid evidence.
"""

import os

import pytest

from inland_worker.connectors.registry import get_connector
from inland_worker.kit import fetch
from inland_worker.kit.testing import assert_valid_evidence

pytestmark = pytest.mark.live

CALIFORNIA = (-124.5, 32.5, -114.1, 42.0)
SB_COUNTY = (-117.8, 33.8, -114.1, 35.9)


@pytest.fixture(autouse=True)
def _real_user_agent(monkeypatch):
    # conftest sets a test UA; live calls should identify the project properly
    ua = (
        os.environ.get("LIVE_NWS_USER_AGENT")
        or "inland-resilience-agent/0.1 (+https://github.com/samin1554/inland-resilience)"
    )
    monkeypatch.setenv("NWS_USER_AGENT", ua)


async def test_wfigs_current_live():
    c = get_connector("wfigs_current")
    result = await fetch(c, c.query(bbox=CALIFORNIA), mode="live")
    assert_valid_evidence(result.items)
    print(f"\nWFIGS: {len(result.items)} current perimeters in California")


async def test_nws_forecast_live():
    c = get_connector("nws_forecast")
    result = await fetch(c, c.query(bbox=(-117.2998, 34.0983, -117.2798, 34.1183)), mode="live")
    assert len(result.items) == 1
    assert_valid_evidence(result.items)
    print(f"\nNWS: {len(result.items[0].properties['periods'])} forecast periods for San Bernardino")


@pytest.mark.skipif(not os.environ.get("FIRMS_MAP_KEY"), reason="FIRMS_MAP_KEY not set in .env")
async def test_firms_live():
    c = get_connector("firms")
    result = await fetch(c, c.query(bbox=SB_COUNTY, params={"days": 5}), mode="live")
    assert_valid_evidence(result.items)
    assert all(os.environ["FIRMS_MAP_KEY"] not in r.url for r in result.responses)
    print(f"\nFIRMS: {len(result.items)} detections in the SB County box (last 5 days)")
