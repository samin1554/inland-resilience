# Section 5: Weather and environment connectors

**Stack:** Python 3.12 · Pydantic · the project's **connector kit** · pytest
**Pair partner:** Section 7 (platform and data infra): together you make scheduled refreshes and caching work.
**Read first:** [Start here](../guides/start-here.md) · [Connector guide](../connectors/connector-guide.md) (**essential**) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

## 1. Your job in plain English

You connect the app to **weather and environmental conditions**, the context that explains *why* fire behaved the way it did:

| Source | What it tells us |
|---|---|
| **National Weather Service (NWS)** | Forecasts for a location, and active weather alerts (e.g. Red Flag Warnings). |
| **California CIMIS** | Daily conditions like evapotranspiration, solar radiation, temperature, humidity and wind, from stations and ~2 km modelled estimates. |

Later (phase two): AirNow air quality, USGS earthquakes, CAL FIRE hazard zones.

Like Section 4, you **translate** each provider's format into our shared *evidence* object, using the lead's connector kit. You write *build the request* and *parse the response*; the kit handles HTTP, keys, retries, caching and recordings.

**Analogy:** you're the weather reporter for a detective. You bring conditions to the case file with exact times and sources, and you're careful to say whether a number was *measured at a station* or *estimated by a model*.

![Ingestion pipeline](../diagrams/ingestion-pipeline.svg)

**Done looks like:** NWS forecast, NWS alerts and CIMIS connectors pass the shared suite offline, have provider docs and fixtures, and never blur a forecast into an observation or an estimate into a measurement.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/connectors/weather/**` | `kit/**`, `data/**` (lead) |
| `apps/worker/tests/connectors/weather/**` | `providers.yaml`: propose entries via PR |
| `apps/worker/tests/fixtures/{nws_forecast,nws_alerts,cimis}/**` | `contracts/**` (lead) |
| `docs/connectors/providers/{nws,cimis}.md` (+ phase-two specs) | fire connectors (S4) |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Forecast vs observation** | A forecast *predicts*; an observation *measured*. Different evidence types, never mixed. |
| **Issued / updated time** | When a forecast was produced. It's the forecast's `observed_at`. Old forecasts get a `stale_forecast` flag. |
| **NWS `/points` discovery** | You ask `/points/{lat},{lon}` and NWS tells you which forecast URLs to use. **Follow those URLs**; never build grid IDs yourself. |
| **User-Agent header** | NWS requires a descriptive `User-Agent` identifying the app. The kit adds it from `NWS_USER_AGENT`. |
| **Station vs spatial (CIMIS)** | Station = a physical instrument; spatial = a ~2 km modelled estimate. You must record which (`provider_type`). |
| **Units** | Always keep units (`unitOfMeasure=M` = metric for CIMIS). Numbers without units are bugs. |
| **Alert** | An official warning. We show it **for context only**, with a limitation telling users to follow official authorities. |
| **Connector, fixture, evidence** | Same as in the [connector guide](../connectors/connector-guide.md). |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Python, typing, Pydantic, pytest | Core | [Python tutorial](https://docs.python.org/3/tutorial/) · [Pydantic](https://docs.pydantic.dev/latest/) · [pytest](https://docs.pytest.org/en/stable/getting-started.html) | Parse a saved JSON file into Pydantic models; test it. |
| JSON + datetimes | Timestamps | [`datetime` docs](https://docs.python.org/3/library/datetime.html) | Parse `2026-09-23T10:00:00-07:00` and convert it to UTC. |
| NWS API | Forecasts + alerts | [weather.gov API docs](https://www.weather.gov/documentation/services-web-api) | In your browser, open `https://api.weather.gov/points/34.1083,-117.2898` and follow its `forecast` link. |
| CIMIS API | Conditions | [CIMIS Web API](https://et.water.ca.gov/Rest/Index) | Register for a free app key and fetch one week for one point. |
| GeoJSON | Output geometry | [geojson.org](https://geojson.org/) | Represent a forecast point and an alert polygon. |

**Learn it with AI:**
```text
Explain the National Weather Service API's /points discovery flow: why we must follow the returned
forecast/forecastHourly/forecastGridData URLs instead of constructing grid IDs, and what fields
tell me when a forecast was issued. Then list failure cases I should handle.
```

## 5. Set up your machine

Same as S4: Python 3.12+, [uv](https://docs.astral.sh/uv/), clone the repo, OpenCode. Get a **CIMIS app key** from the CIMIS site and put it only in your local `.env` as `CIMIS_APP_KEY=...`. Set `NWS_USER_AGENT` in `.env` to something like `inland-resilience-agent/0.1 your-email@example.com`. Never commit keys or paste them into AI tools.

## 6. Build it step by step

### S5-1 NWS forecast connector
- **Goal:** point in → `weather_forecast` evidence out.
- **Steps:** spec first ([nws.md](../connectors/providers/nws.md)); record fixtures for `/points` and the forecast; `build_requests` asks `/points`; the kit follows the returned `forecast` URL (it must stay on `api.weather.gov`); `parse` keeps period times and units, and sets `observed_at` to the issue/update time.
- **AI prompt:**
  ```text
  Following docs/connectors/connector-guide.md and docs/connectors/providers/nws.md, plan an NWS
  forecast connector as a two-step request (points -> forecast URL). Explain how the kit restricts
  followed URLs to allowed_hosts. Show the field mapping and write tests first from fixtures.
  ```
- **Tests:** shared suite + a followed URL on another host is refused; an old forecast gets `stale_forecast`; a missing forecast → `Missing`, not an empty success.
- **Done when:** the suite passes offline and the lead approves `nws.md`.

### S5-2 NWS alerts connector
- **Goal:** active California alerts, refreshed on a schedule.
- **Steps:** `/alerts/active?area=CA` and `?point=`; agree with the lead which evidence type alerts use (open question in `nws.md`); every item carries *"Shown for context only. Follow official local authorities for emergency guidance."*
- **Important:** alert text comes from outside. It's *data*, and the agent must never follow instructions inside it (S8 and the lead test prompt injection).
- **Tests:** no alerts → `[]`; alert geometry missing → flagged, not dropped.

### S5-3 CIMIS connector
- **Goal:** daily conditions with honest provenance.
- **Steps:** metric units; set `properties.provider_type` to `station` or `spatial`; carry CIMIS QC codes into `quality_flags`; spatial results get the "modelled estimate" limitation.
- **Tests:** a spatial result is never labelled a station measurement; future dates → empty.

### S5-4 Phase two (only after the historical-fire workflow works end to end)
AirNow via `/aq/observation/current/ziplatlong/` (**not** the legacy endpoint retiring Sep 30 2026), USGS earthquakes, CAL FIRE Fire Hazard Severity Zones. Start each with a provider spec from the [template](../connectors/provider-spec-template.md).

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Connector kit + suite | Lead | Plain pytest on `parse` functions |
| Alert evidence type decision | Lead | Draft as `weather_observation` + `kind: alert` |

| Others need from you | Who |
|---|---|
| Schedules (`ingestion.schedule`) for alerts | S7 (ingest mode) |
| Weather context evidence | Lead (agent), S8 (verification) |

## 8. When you're stuck

Connector guide + official provider docs → OpenCode Plan mode → S7 (your pair) for caching/scheduling → the lead for kit questions → team chat with the fixture, the error and your branch.

## 9. Coming from the lead

- [ ] Connector kit v0, including support for following URLs (needed by NWS)
- [ ] Evidence type decision for alerts
- [ ] Choice of representative point for large areas
- [ ] Rate-limit settings once live usage is observed
