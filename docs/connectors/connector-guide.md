# Connector Guide

**Owner:** Lead · **Readers:** Sections 4, 5, 6, 7, 8 and anyone who needs data
**Status:** Design, v0.2 (no code yet) · **Just need data?** See the [data catalog](../data-catalog.md) · **Related:** [ADR-001](../adr/ADR-001-hybrid-ingestion.md), [ADR-006](../adr/ADR-006-cache-and-snapshots.md), [ingestion diagram](../diagrams/ingestion-pipeline.html)

This guide explains how data gets into the Inland Resilience Agent. It covers two audiences:

- **Connector authors** (Sections 4–5, and 6 for Earth Engine) add a provider by **copying the lead's reference connector for that pattern** (§3.0) and changing the URL and field mapping.
- **Data consumers** (the agent, Section 8, anyone else in the worker) get normalized evidence from one function and never talk to a provider directly.

> **The one rule:** only the connector kit makes network calls to providers. Nothing else in the codebase imports `httpx`, calls a URL, or reads a provider API key.

---

## 1. The big picture

```text
provider ──HTTP──▶ connector kit ──Evidence──▶ ingest mode ──▶ PostGIS cache
                        ▲                                         │
                        └──── live fetch if stale ◀── inland_data ◀┘ ◀── agent tools, sections
```

There are three parts:

| Part | Owner | What it is |
|---|---|---|
| **Connector kit** (`inland_worker/kit/`) | Lead | Base classes, the allowlisted HTTP client, the provider registry, cache and fixture machinery, and the shared test suite. |
| **Reference connectors** (`firms.py`, `wfigs.py`, `nws_forecast.py`, `kit/compute.py`) | Lead | One fully working connector per source pattern: the templates everyone copies. |
| **Connectors** (`inland_worker/connectors/<group>/`) | Sections 4–5 | One small class per remaining provider, copied from the matching reference. They build requests and parse responses into `Evidence`, and do nothing else. |
| **`inland_data` API** (`inland_worker/data/`) | Lead | The only way to read data. It decides between cache and a live fetch, and labels freshness. |

Scheduling (`inland_worker/ingest/`, Section 7) runs connectors on a timer through the same kit.

---

## 2. Ingestion classes

Every provider is assigned exactly one class in `providers.yaml`. The class decides how its data arrives.

| Class | Behaviour | Providers (MVP) |
|---|---|---|
| `reference` | Synced nightly (or by hand) into PostGIS reference tables. Jobs never wait on the provider. | SB County boundary, CAL FIRE historical perimeters |
| `near_real_time` | Refreshed on a schedule into the cache. Jobs read the cache and call live only if it's stale. | NASA FIRMS, NIFC WFIGS current perimeters, NWS active alerts |
| `on_demand` | Fetched during a job, with a short-lived cache keyed by the query. | NWS point forecast, CIMIS |
| `compute` | Server-side computation during a job. Results are cached by area + dates + collection. | Google Earth Engine (Sentinel-2) |

---

## 3. Writing a connector

### 3.0 Start from a reference connector

Every source is one of four patterns, and the lead ships a fully working, tested connector for each. **Never start from a blank file.** Copy the reference that matches your source:

| Pattern | Reference (lead) | Use it for |
|---|---|---|
| Keyed API (CSV/JSON + key) | `connectors/fire/firms.py` | CIMIS, AirNow |
| ArcGIS feature service (paging, ArcGIS JSON → GeoJSON) | `connectors/fire/wfigs.py` | CAL FIRE, county boundary, hazard zones, county layers |
| Follow-the-link API | `connectors/weather/nws_forecast.py` | NWS alerts, USGS |
| Earth Engine compute | `kit/compute.py` | Sentinel-2 / Landsat / ECOSTRESS / GOES analysis (S6) |

Each reference comes with its fixtures, tests and a filled-in provider spec. Copy all four parts, not just the code.

### 3.1 The shape

A connector is two **pure** methods plus a parameters model. The kit does all I/O: HTTP, auth, retries, timeouts, size caps, caching, fixtures and trace records.

```python
# inland_worker/connectors/fire/firms.py
from inland_worker.kit import BaseConnector, ProviderQuery, ProviderRequest, RawResponse
from inland_worker.contracts import Evidence

class FirmsParams(BaseModel):
    source: Literal["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT", "LANDSAT_NRT"] = "VIIRS_NOAA21_NRT"
    days: conint(ge=1, le=5) = 2

class FirmsConnector(BaseConnector):
    provider_id = "firms"                       # must match providers.yaml
    evidence_types = {"satellite_detection"}
    Params = FirmsParams

    def build_requests(self, q: ProviderQuery[FirmsParams]) -> list[ProviderRequest]:
        west, south, east, north = q.bbox()
        return [ProviderRequest(path=f"/{{MAP_KEY}}/{q.params.source}/{west},{south},{east},{north}/{q.params.days}")]

    def parse(self, resp: RawResponse, q: ProviderQuery[FirmsParams]) -> list[Evidence]:
        ...  # CSV rows -> Evidence(evidence_type="satellite_detection", ...)
```

What the kit guarantees to your connector:

- `{{MAP_KEY}}`-style placeholders are filled from the env var named in `providers.yaml`. The secret never appears in your code, logs or traces.
- Requests can only go to the `allowed_hosts` for your provider. Any other host is rejected before it's sent.
- `resp` has already passed the timeout, retry and size limits, and carries `retrieved_at` and the provider's own update time if it sent one.
- In fixture mode, `resp` comes from a recorded file. Your `parse` can't tell the difference, and that's the point.

### 3.2 Rules for `parse`

1. **Every item gets `observed_at`** (acquisition or report time from the provider) **and `retrieved_at`** (from `resp`). Never substitute one for the other.
2. **Geometry is WGS84 GeoJSON** (`EPSG:4326`). Convert ArcGIS JSON to GeoJSON here.
3. **Add the default limitations** from `providers.yaml`, plus any row-specific ones.
4. **Quality problems go in `quality_flags`**, not exceptions: missing fields, low confidence, generalized geometry, duplicates.
5. **Unknown fields are ignored**, not fatal. A provider adding a column must not break us.
6. **Empty is a valid answer.** Return `[]`. Never invent a placeholder item.
7. **No agent inference here.** A connector only produces the observation, measurement, official or forecast evidence types.

### 3.3 Adding a provider, step by step

```bash
make new-connector NAME=airnow GROUP=weather PATTERN=keyed   # keyed | arcgis | follow_link
```

This copies the matching reference connector and scaffolds:

```text
apps/worker/src/inland_worker/connectors/weather/airnow.py   # class stub
apps/worker/tests/connectors/test_airnow.py                  # shared suite wired in
apps/worker/tests/fixtures/airnow/                           # put recordings here
docs/connectors/providers/airnow.md                          # copied from the template
```

Then:

1. Fill in `docs/connectors/providers/airnow.md` from the [template](provider-spec-template.md) **first**. Your PR reviewer reads this before the code.
2. Add the `airnow:` block to `providers.yaml` (§4). The lead reviews every change to this file.
3. Record fixtures (§5).
4. Implement `build_requests` and `parse` until the shared suite passes (§6).
5. Open a PR titled `feat/airnow-connector`.

---

## 4. `providers.yaml`: the registry and allowlist

One file, `apps/worker/config/providers.yaml`, is the single source for endpoints and limits. Numbers below are **starting values** to tune once live traffic is observed.

```yaml
firms:
  display_name: NASA FIRMS
  base_url: https://firms.modaps.eosdis.nasa.gov/api/area/csv
  allowed_hosts: [firms.modaps.eosdis.nasa.gov]
  auth: { type: path_placeholder, placeholder: MAP_KEY, env: FIRMS_MAP_KEY }
  timeout_s: 20
  max_response_bytes: 10_000_000
  retries: { max: 3, backoff: exponential, on: [429, 502, 503, 504, timeout] }
  cache: { key: [source, bbox, days], ttl: 30m }
  ingestion: { class: near_real_time, schedule: "*/30 * * * *", default_area: sb_county_bbox }
  evidence_types: [satellite_detection]
  source_url: https://firms.modaps.eosdis.nasa.gov/
  default_limitations:
    - A thermal anomaly is not an officially confirmed wildfire.
```

| Field | Meaning |
|---|---|
| `base_url`, `allowed_hosts` | The only places the kit may send requests for this provider. NWS "follow the URL" links must also match `allowed_hosts`. |
| `auth` | `none`, `header`, `query_param` or `path_placeholder`, plus the **name** of the env var (never the value). |
| `headers` | Static headers, e.g. NWS `User-Agent` from `NWS_USER_AGENT` and `Accept: application/geo+json`. |
| `timeout_s`, `max_response_bytes` | Hard limits. Required for every provider (spec §13). |
| `retries` | Bounded retries (Tenacity). Never unbounded. |
| `cache.key`, `cache.ttl` | Which query fields form the cache key, and how long a cached result is fresh. |
| `ingestion.class`, `ingestion.schedule` | See §2. `schedule` only applies to `reference` and `near_real_time`. |
| `evidence_types` | What this provider may emit. The kit rejects anything else. |
| `default_limitations` | Attached to every item from this provider. |

Shared named areas (`sb_county_bbox = -117.8,33.8,-114.1,35.9`) live in the same file under `areas:`.

---

## 5. Fixtures: working without API keys

Every connector ships with recorded responses so anyone can run tests offline (spec §19).

```bash
make record-fixture PROVIDER=firms CASE=line_fire_2024   # needs the real key, run once
make test-connector PROVIDER=firms                       # uses recordings, no key needed
```

- Recordings live in `apps/worker/tests/fixtures/<provider>/<case>/` as the raw response plus a `meta.json` holding the request, status and timestamps.
- The recorder **strips secrets** (keys in paths, query strings and headers) before writing. CI fails if a fixture contains a known key pattern.
- Each provider needs at least these cases: `success`, `empty`, `malformed`, and `extra_fields` (the recorded success with an unexpected column added).
- Set `INLAND_DATA_MODE=fixture` to make the whole worker, including the agent, run on recordings. This is how Milestone 1 works.

---

## 6. The shared connector test suite

You don't write these tests. You get them by registering your connector. Each one maps to the spec §21 checklist:

| Test | Passes when |
|---|---|
| `test_success` | The `success` fixture parses to ≥1 valid `Evidence` that matches `evidence.schema.json`. |
| `test_empty` | The `empty` fixture returns `[]`, not an error. |
| `test_timeout` | A simulated timeout ends in a clean `ProviderTimeout` after the configured retries. |
| `test_rate_limited` | A simulated 429 is retried with backoff, then surfaces as `ProviderRateLimited`. |
| `test_malformed` | The `malformed` fixture raises `ProviderParseError` or returns flagged items, and never crashes. |
| `test_schema_drift` | The `extra_fields` fixture parses the same as `success`. |
| `test_timestamps` | Every item has `observed_at` and `retrieved_at`, and they aren't equal by construction. |
| `test_limitations` | Every item carries the provider's default limitations. |
| `test_no_secrets` | No env-var value appears in the evidence, trace or logs. |
| `test_fixture_live_parity` *(nightly, needs keys)* | Live output has the same schema, the same evidence types and the same property keys as the fixture output. |

Add provider-specific tests in the same file as needed, e.g. FIRMS confidence mapping.

---

## 7. Reading data: the `inland_data` API

This is what the agent's tools and everyone else call. It hides the cache, freshness rules, live fallback and trace recording.

```python
from inland_worker.data import get_evidence, get_reference_layer

result = await get_evidence(
    "firms",
    area=aoi,                                   # GeoJSON geometry, already validated by Go
    date_range=DateRange(start, end),
    params={"source": "VIIRS_NOAA21_NRT", "days": 2},
    job_id=job_id,                              # links the call into tool_executions
)

result.items        # list[Evidence]
result.freshness    # Fresh | Stale(age, reason) | Missing(reason)
result.origin       # "cache" | "live" | "snapshot" | "fixture"

boundary = await get_reference_layer("sb_county_boundary")   # reference class only
```

How a call is resolved:

1. **Cache hit, fresh.** Return it with `origin="cache"`.
2. **Cache stale or missing.** Fetch live through the kit, store the result, and return it with `origin="live"`.
3. **Live fetch fails.** Return the last-known-good snapshot with `freshness=Stale(...)` and add the quality flag `stale_snapshot` to every item (spec §15).
4. **No snapshot either.** Return `Missing(reason)` with no items. The agent must say "insufficient evidence", never "nothing happened".

Every call writes one `tool_executions` row (tool name, summarized inputs, timings, status, error code) with secrets redacted.

---

## 8. Ownership and review

| Path | Owner | Reviewer |
|---|---|---|
| `inland_worker/kit/` (incl. `compute.py`), `inland_worker/data/`, `config/providers.yaml` | Lead | Section 7 |
| Reference connectors `connectors/fire/{firms,wfigs}.py`, `connectors/weather/nws_forecast.py` + their tests and fixtures | Lead | Sections 4, 5 |
| All other files in `inland_worker/connectors/fire/` | Section 4 | Lead |
| All other files in `inland_worker/connectors/weather/` | Section 5 | Lead |
| `inland_worker/satellite/` (uses the kit's `compute` path) | Section 6 | Lead |
| `inland_worker/ingest/` | Section 7 | Lead |
| `tests/fixtures/<provider>/` | That provider's connector owner | Anyone |

## 9. Provider specs

- [Data catalog](../data-catalog.md): every source, its `provider_id`, owner and status

- [Template](provider-spec-template.md)
- [NASA FIRMS](providers/firms.md) · [NIFC WFIGS](providers/wfigs.md) · [CAL FIRE historical](providers/calfire-historical.md) · [SB County boundary](providers/sb-county-boundary.md)
- [National Weather Service](providers/nws.md) · [CIMIS](providers/cimis.md) · [Earth Engine Sentinel-2](providers/gee-sentinel2.md)
