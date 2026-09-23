# Section 5: Weather and environment connectors

**Stack:** Python 3.12, Pydantic, the connector kit, pytest · **Pairs with:** S7

## Scope
MVP: [NWS forecast + alerts](../connectors/providers/nws.md), [CIMIS](../connectors/providers/cimis.md). Phase two (only after the historical-fire workflow works end to end, spec §26): AirNow (use `/aq/observation/current/ziplatlong/`, **not** the legacy endpoint retiring Sep 30 2026), USGS earthquakes, CAL FIRE Fire Hazard Severity Zones.

## Owned paths
`apps/worker/src/inland_worker/connectors/weather/**` · `apps/worker/tests/connectors/weather/**` · `apps/worker/tests/fixtures/{nws_forecast,nws_alerts,cimis}/**` · `docs/connectors/providers/{nws,cimis}.md` (+ phase-two specs)

## First tickets

**S5-1 NWS forecast connector.** *Input:* a point in the area. *Output:* `weather_forecast` evidence. *Acceptance:* follows the `/points` response URLs (no hand-built grid IDs); sends `User-Agent` from `NWS_USER_AGENT`; the suite passes. *Failure test:* a followed URL on another host is refused by the kit.

**S5-2 NWS alerts connector.** CA active alerts as `near_real_time`. Agree the evidence type for alerts with the lead (open question in `nws.md`). Every alert carries the "follow official authorities" limitation.

**S5-3 CIMIS connector.** Must set `properties.provider_type` = `station` | `spatial`. *Acceptance:* a spatial result is never labelled a station measurement.
