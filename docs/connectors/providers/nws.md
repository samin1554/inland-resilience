# Provider spec: National Weather Service API

| Field | Value |
|---|---|
| `provider_id` | `nws_forecast` (point forecast) and `nws_alerts` (active alerts) |
| Owner | Section 5 |
| Ingestion class | `nws_alerts`: `near_real_time` (CA alerts every 15 min). `nws_forecast`: `on_demand` |
| Evidence types | `weather_forecast`; alerts are stored as `weather_observation` with `properties.kind = "alert"` (TODO: confirm with the lead, or add an evidence type via a contract change) |
| Auth | none. **Required headers**: `User-Agent` ← env `NWS_USER_AGENT`, `Accept: application/geo+json` |
| Docs | https://www.weather.gov/documentation/services-web-api |
| Status | draft |

## 1. Endpoints
```text
Base: https://api.weather.gov

GET /points/{lat},{lon}                  # discover forecast URLs, e.g. /points/34.1083,-117.2898
    → follow properties.forecast, properties.forecastHourly, properties.forecastGridData
GET /alerts/active?area=CA
GET /alerts/active?point={lat},{lon}
```
`allowed_hosts: [api.weather.gov]`. Followed URLs must also match this host, so the kit refuses anything else.

**Don't construct grid identifiers manually.** Always follow the URLs returned by `/points` (spec §11.6).

## 2. Query parameters
Point = the area's representative point (centroid, or a point-on-surface for odd shapes). TODO: decide how to handle large areas that span several forecast grids.

## 3. Limits and behaviour
- Cache `/points` results for a long time (the grid mapping rarely changes). Proposed forecast TTL 1 h, alerts 15 min.
- Handle delayed or missing observations explicitly (spec §11.6): a missing forecast is `Missing`, not an empty success.

## 4. Field → Evidence mapping (forecast)
| Field | Evidence field |
|---|---|
| forecast period `startTime`/`endTime` | `observed_at` = issuance time (`generatedAt` / `updateTime`); period times in `properties` |
| temperature, wind, `shortForecast` | `properties.*` with units kept |
| forecast office/grid | `properties.grid` |

## 5. Quality flags
`stale_forecast` when `updateTime` is older than 12 h (proposed threshold).

## 6. Limitations
- Forecast: *Forecasts are predictions and may change; check weather.gov for current conditions.*
- Alerts: *Shown for context only. Follow official local authorities for emergency guidance.* (spec §15: never generate evacuation instructions)

## 7. Fixture plan
`/points` + forecast for San Bernardino (34.1083,-117.2898); `alerts/active?area=CA` on a day with alerts, and a point with none for `empty`.
