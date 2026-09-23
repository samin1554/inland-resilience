# Section 4: Fire data connectors

**Stack:** Python 3.12 · Pydantic · the project's **connector kit** · pytest
**Pair partner:** Section 1 (map frontend): check that your data draws correctly on the map.
**Read first:** [Start here](../guides/start-here.md) · [Connector guide](../connectors/connector-guide.md) (**essential**) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

## 1. Your job in plain English

You connect the app to **the sources of fire data**:

| Source | What it tells us |
|---|---|
| **NASA FIRMS** | Satellites spotted something hot here, at this time (a *thermal detection*, not a confirmed fire). |
| **NIFC WFIGS current perimeters** | The official outline of fires burning right now. |
| **CAL FIRE historical perimeters** | Official outlines of past fires (e.g. the 2024 Line Fire). |
| **San Bernardino County boundary** | The shape of the county, which we use to check requests are in scope. |

Each source speaks its own "language" (CSV, ArcGIS JSON, GeoJSON, different field names and time formats). Your job is to **translate each one into our single shared format**: the *evidence* object. After you, nobody else in the project has to know how FIRMS formats its CSV.

**Analogy:** you're a translator at the UN. Each delegate speaks a different language; you turn everything into one language, and you must preserve meaning exactly, including the caveats.

The lead built the **connector kit**, which does all the hard plumbing (HTTP requests, API keys, retries, timeouts, caching, test recordings). You write **two small, pure functions** per source: *build the request* and *parse the response*.

![Ingestion pipeline](../diagrams/ingestion-pipeline.svg)

**Done looks like:** each of the four sources has a connector that passes the shared test suite offline, a provider spec doc, and recorded fixtures, and its output shows up correctly on S1's map.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/connectors/fire/**` | `apps/worker/src/inland_worker/kit/**`, `data/**` (lead) |
| `apps/worker/tests/connectors/fire/**` | `apps/worker/config/providers.yaml`: **propose** entries via PR; the lead reviews |
| `apps/worker/tests/fixtures/{firms,wfigs_current,calfire_historical,sb_county_boundary}/**` | `contracts/**` (lead) |
| `docs/connectors/providers/{firms,wfigs,calfire-historical,sb-county-boundary}.md` | other connectors (S5), satellite code (S6) |

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Connector** | A class that knows one provider: how to ask (`build_requests`) and how to translate the answer (`parse`). |
| **Evidence object** | Our one shared format: type, source, `observed_at`, `retrieved_at`, geometry, properties, quality flags, limitations, source URL. |
| **Pure function** | Same input → same output, no network or files. `parse` is pure, which makes it easy to test. |
| **Fixture / recording** | A saved real response, replayed in tests so nobody needs API keys. |
| **`observed_at` vs `retrieved_at`** | When the satellite or agency saw it vs when *we* downloaded it. Never mix them up. |
| **GeoJSON / WGS84** | Standard map-shape JSON using longitude/latitude (`[lng, lat]`). |
| **ArcGIS FeatureServer** | Esri's web service used by many agencies. You query it with URL parameters; results can be paged. |
| **Pydantic model** | A Python class that validates data types for you. |
| **Quality flag** | A note like `low_confidence` attached to an item, instead of throwing it away. |
| **Limitation** | Plain-language caveat shown to users, e.g. *"A thermal anomaly is not an officially confirmed wildfire."* |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| Python 3.12 | The language | [docs.python.org/3/tutorial](https://docs.python.org/3/tutorial/) | Read a CSV with the `csv` module and convert rows to dicts. |
| Type hints | Clear interfaces | [typing docs](https://docs.python.org/3/library/typing.html) | Type a function `parse(rows: list[dict]) -> list[Detection]`. |
| Pydantic | Validation | [docs.pydantic.dev](https://docs.pydantic.dev/latest/) | Model a FIRMS row; see what happens with a bad value. |
| pytest | Tests | [docs.pytest.org](https://docs.pytest.org/en/stable/getting-started.html) | Test your CSV parser with a small fixture file. |
| GeoJSON | Output geometry | [geojson.org](https://geojson.org/) | Convert 3 lat/lon rows into a GeoJSON FeatureCollection. |
| ArcGIS REST query | WFIGS, CAL FIRE, county | [Esri: Query (Feature Service/Layer)](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/) | Open the CAL FIRE query URL from the provider spec in your browser with `f=geojson`. |
| NASA FIRMS API | Hotspots | [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/) | Get a free MAP_KEY and fetch 1 day for the county box in your browser. |

**Learn it with AI:**
```text
I'm writing a Python function that converts NASA FIRMS CSV rows into GeoJSON point features.
Explain acq_date + acq_time (HHMM, UTC) and how to turn them into a timezone-aware ISO 8601
datetime. Then list 5 edge cases I should test (empty file, missing frp, extra column, ...).
```

## 5. Set up your machine

```bash
# Python 3.12+: https://www.python.org/downloads/  (or brew install python@3.12)
# uv (fast Python package manager, recommended): https://docs.astral.sh/uv/
git clone https://github.com/samin1554/inland-resilience.git
```
Get your own free **FIRMS MAP_KEY** at https://firms.modaps.eosdis.nasa.gov/api/map_key/. Put it only in your local `.env` as `FIRMS_MAP_KEY=...`. **Never** commit it or paste it into an AI chat. WFIGS, CAL FIRE and the county boundary need no key.

## 6. Build it step by step

Always follow the order **spec → fixtures → parse → tests → PR**. The [connector guide §3](../connectors/connector-guide.md#3-writing-a-connector) has the full shape.

### S4-1 FIRMS provider spec + fixtures
- **Goal:** understand FIRMS completely before coding.
- **Steps:** open [firms.md](../connectors/providers/firms.md), resolve its `TODO`s (rate limit, confidence values per source), then record four fixtures with `make record-fixture` (once the kit exists; until then save raw CSV files by hand): `success`, `empty`, `malformed`, `extra_fields`.
- **AI prompt:**
  ```text
  Read docs/connectors/providers/firms.md and the FIRMS Area API docs. Help me list every field I
  get back, what each means, its units, and how it maps to our evidence object. Flag anything in
  the spec that seems wrong or unclear. Don't write code.
  ```
- **Check yourself:** the fixtures contain **no** MAP_KEY (check the file text).
- **Done when:** the lead approves `firms.md` in a PR.

### S4-2 FIRMS connector (your first real deliverable)
- **Goal:** bbox + source + days in → list of `satellite_detection` evidence out.
- **Steps:** implement `build_requests` (URL path from the params) and `parse` (CSV → evidence). `acq_date` + `acq_time` → UTC `observed_at`; keep `confidence` raw plus a `confidence_scheme`; add the default limitation.
- **AI prompt:**
  ```text
  Following docs/connectors/connector-guide.md section 3, plan FirmsConnector in
  connectors/fire/firms.py. build_requests and parse must be pure. Show the field mapping table
  you'll implement and the quality flags you'll add. Then write the tests first against the
  fixtures in tests/fixtures/firms/.
  ```
- **Tests:** the shared suite (automatic) plus your own: time conversion, confidence mapping, the `missing_frp` flag.
- **Common mistakes:** `[lat, lng]` order (must be `[lng, lat]`); a naive datetime without a timezone; dropping rows with a missing field instead of flagging them.
- **Done when:** `make test-connector PROVIDER=firms` passes offline, and S1 displays your fixture output correctly.

### S4-3 County boundary connector
- **Goal:** the county shape as valid GeoJSON, used by S3 for request checks and by S1 for the map.
- **Steps:** the query returns **ArcGIS JSON** (`f=json`), so convert rings to a GeoJSON (Multi)Polygon; validate it; save it as `database/fixtures/sb_county_boundary.geojson` for S7's seed (coordinate the path with S7).
- **Tests:** the output is a valid polygon; coordinates are within the expected county bounding box.

### S4-4 WFIGS current + CAL FIRE historical perimeters
- **Goal:** official perimeters as `official_perimeter` evidence.
- **Steps:** handle ArcGIS **paging** (`exceededTransferLimit`); store the source's update time on every feature; CAL FIRE dates are epoch milliseconds, so convert to UTC; add the `possible_duplicate` flag for the same name + year with overlapping shapes.
- **Tests:** a paging test with a two-page fixture; the empty county (no current fires) returns `[]`.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Connector kit + shared test suite | Lead | Write `parse` as plain functions with pytest, then plug them in |
| Evidence schema | Lead | The example in the connector guide |

| Others need from you | Who |
|---|---|
| Evidence that renders on the map | S1 |
| County boundary seed | S7, S3 |
| Perimeters for corroboration | S8 |
| Scheduled refresh entries | S7 (ingest mode) |

## 8. When you're stuck

Re-read the connector guide and the provider's official docs → OpenCode in Plan mode → S1 (your pair) for "does it draw right?" → the lead for anything about the kit → team chat with your fixture, the error and your branch name.

## 9. Coming from the lead

- [ ] Connector kit v0: `BaseConnector`, `make new-connector`, `make record-fixture`, shared suite
- [ ] Final `evidence.schema.json` + example
- [ ] `providers.yaml` entries to extend
- [ ] Decision on FIRMS historical archive access (see the open question in `firms.md`)
