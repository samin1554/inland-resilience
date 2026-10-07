# ADR-013: "Active now" activity feed

## Status
Accepted (Oct 2026). Adds `GET /v1/activity` to `contracts/openapi.yaml` (contract change). Proven on the lead's
`demo/full-stack` branch, whose code is the reference implementation for every part below.

## Context
Users had to know where to look: draw an area or pick a preset. The data we already pull is national (FIRMS VIIRS
sees thousands of detections across the US in a typical 2-day window), so the app can lead people to where
satellites see heat right now and let them analyse it in one click.

## Decision
- **The worker builds a snapshot; the API only serves it.** A worker command (`python -m inland_worker activity`,
  its own compose service, every 30 min) fetches NASA FIRMS VIIRS NOAA-21, NOAA-20 and Suomi-NPP for `conus_bbox`,
  `alaska_bbox` and `hawaii_bbox` (last 2 days) and NIFC WFIGS current perimeters through `get_evidence()`, so
  caching, traces, stale/missing handling and fixture mode are the same as everywhere else (ADR-001, ADR-006).
  The Go API reads the newest snapshot from the database. No provider calls from the API.
- **Deterministic clustering**, never the model:
  - detections inside the US outline (ADR-012) are snapped to a 0.05° (~5 km) grid; touching cells (8-way) form a
    cluster; per cluster: detection count, high-confidence count, max/total FRP, first/last seen, footprint,
    satellites;
  - **official match:** the current WFIGS perimeter with the largest overlap gives the incident name, acres,
    containment and incident type (`prescribed burn` is said as such); otherwise the **nearest** current perimeter
    within 50 km is reported as context only;
  - **place:** county + state of the centre from `config/regions/us_counties.geojson`;
  - **rank** = `3 × high-confidence + detections + ln(1 + total FRP)`, then most recent; top 50 kept;
  - **suggested analysis area** = cluster bbox + ~3 km, shrunk to ≤ 5,000 km², clipped ~50 m inside the US outline,
    so it passes `POST /v1/analyses` validation unchanged.
- **History** (for trends): per 0.05° cell, the distinct UTC days with detections in the last 14 days; snapshots kept
  48 h so each refresh can compare with ~24 h ago.
  - `trend`: `new` (no detections in these cells before the last 24 h), else `growing` / `stable` / `shrinking`
    against the same cells ~24 h ago (±25 %); `null` until there is enough history (a limitation says so).
  - `persistent_heat_source`: detections on ≥ 5 of the last 14 days and no official perimeter (typical of gas
    flares, refineries, steel mills). Such clusters rank lower (score × 0.3) and are hidden by default in the UI,
    never deleted; an official perimeter always overrides it, so a long wildfire is never demoted.
- **Labels:** `officially_reported` only with an overlapping official perimeter; otherwise `unverified_detection`.
  Every snapshot carries its sources and limitations; an empty feed says it doesn't mean nothing is burning; an
  unavailable source still produces a snapshot whose limitations say what is missing.

## Who builds what
| Part | Owner | Demo reference |
|---|---|---|
| Contract (`GET /v1/activity`, `ActivitySnapshot`, `ActivityCluster`) | Lead | `contracts/openapi.yaml` (this ADR) |
| Snapshot builder, clustering, history, refresh loop | Lead + S7 (it is ingest-mode work) | `apps/worker/src/inland_worker/activity/` |
| Tables (`activity_snapshots`, `activity_clusters`, `activity_cells`) | S7 | `database/migrations/0003_*`, `0004_*` |
| `GET /v1/activity` handler (bbox + limit, `503 ACTIVITY_NOT_READY`) | S3 | `apps/api/internal/httpapi/activity.go` |
| "Active now" tab: list, filters, map layer, "Analyse this area", shareable URLs | S1 + S2 | `apps/web/src/activity/` |

## Consequences and limits
- FIRMS pixels are ~375 m and arrive 3–4 h after the overpass; clouds and smoke hide fires; industrial heat, gas
  flares and agricultural/prescribed burns also appear. All of this is in every snapshot's limitations.
- FIRMS key use: 9 area calls per refresh (3 satellites × 3 areas), 18 per hour, far under the key's limits.
- The 5 km grid trades merging nearby fires against splitting large ones; it suits wildfire-scale clusters.
- Persistence needs about a week of history before it shows on real data (on the demo, 12 of 50 clusters were
  flagged after four days, including the Gary, Indiana steel mills).
- National current-perimeter pulls need `wfigs_current` `max_offset` (~100 m) and small pages to stay under
  `max_response_bytes`.
