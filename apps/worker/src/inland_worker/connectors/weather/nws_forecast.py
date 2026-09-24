"""National Weather Service point forecast.

REFERENCE CONNECTOR for the *follow-the-link* pattern. Copy it for NWS alerts, USGS, ...
    make new-connector NAME=<id> GROUP=<fire|weather> PATTERN=follow_link

What makes this pattern tricky, and how it's handled here:
- Step 1 asks /points/{lat},{lon}; NWS answers with the forecast URL to use. Never build grid IDs by hand.
- `follow()` returns that URL; the kit refuses it unless its host is in allowed_hosts (api.weather.gov).
- NWS requires a User-Agent: providers.yaml fills it from NWS_USER_AGENT.
- A forecast is issued at a time: that issue/update time is `observed_at`, not the forecast period.
Spec: docs/connectors/providers/nws.md
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from inland_worker.contracts.models import Evidence, EvidenceType
from inland_worker.kit.connector import BaseConnector, ProviderQuery, ProviderRequest, RawResponse

STALE_AFTER = timedelta(hours=12)


class NwsForecastParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hourly: bool = False


class NwsForecastConnector(BaseConnector):
    provider_id = "nws_forecast"
    evidence_types = frozenset({EvidenceType.WEATHER_FORECAST})
    Params = NwsForecastParams

    def build_requests(self, query: ProviderQuery) -> list[ProviderRequest]:
        lon, lat = query.representative_point()
        return [ProviderRequest(path=f"/points/{lat:.4f},{lon:.4f}", label="points")]

    def follow(self, response: RawResponse, query: ProviderQuery) -> list[ProviderRequest]:
        if response.request.label != "points":
            return []
        p: NwsForecastParams = query.params  # type: ignore[assignment]
        props = response.json()["properties"]
        url = props["forecastHourly" if p.hourly else "forecast"]
        return [ProviderRequest(url=url, label="forecast")]

    def parse(self, responses: Sequence[RawResponse], query: ProviderQuery) -> list[Evidence]:
        points = next(r for r in responses if r.request.label == "points").json()["properties"]
        forecast_resp = next((r for r in responses if r.request.label == "forecast"), None)
        if forecast_resp is None:
            raise ValueError("points response had no forecast link to follow")
        forecast = forecast_resp.json()
        props = forecast["properties"]
        periods = props.get("periods") or []
        if not periods:
            return []

        issued_raw = props.get("updateTime") or props.get("generatedAt")
        flags: list[str] = []
        if issued_raw:
            issued = datetime.fromisoformat(issued_raw)
        else:
            flags.append("missing_issue_time")
            issued = forecast_resp.retrieved_at
        if forecast_resp.retrieved_at - issued > STALE_AFTER:
            flags.append("stale_forecast")

        lon, lat = query.representative_point()
        geometry = forecast.get("geometry") or {"type": "Point", "coordinates": [lon, lat]}
        grid = f"{points.get('gridId')}/{points.get('gridX')},{points.get('gridY')}"
        return [
            self.evidence(
                evidence_type=EvidenceType.WEATHER_FORECAST,
                observed_at=issued,
                retrieved_at=forecast_resp.retrieved_at,
                geometry=geometry,
                source_record_id=f"{grid}:{issued.isoformat()}",
                properties={
                    "office": points.get("gridId"),
                    "grid": grid,
                    "hourly": "hourly" in (forecast_resp.request.url or ""),
                    "generated_at": props.get("generatedAt"),
                    "periods": [
                        {
                            "name": per.get("name"),
                            "start": per.get("startTime"),
                            "end": per.get("endTime"),
                            "is_daytime": per.get("isDaytime"),
                            "temperature": per.get("temperature"),
                            "temperature_unit": per.get("temperatureUnit"),
                            "precip_probability_pct": (per.get("probabilityOfPrecipitation") or {}).get(
                                "value"
                            ),
                            "wind_speed": per.get("windSpeed"),
                            "wind_direction": per.get("windDirection"),
                            "short_forecast": per.get("shortForecast"),
                        }
                        for per in periods
                    ],
                },
                quality_flags=flags,
            )
        ]
