# ADR-012: Supported region is the United States (50 states + DC)

## Status
Accepted (Oct 2026). Supersedes the San Bernardino County scope of the spec (§11.2) and [ADR-011](ADR-011-statewide-region.md).
Proven end to end on the lead's `demo/full-stack` branch (reference implementation, not merged).

## Context
Nothing in the architecture depends on the county: per-job cost is bounded by the area limit (5,000 km²), not by
the region, and the core sources already cover far more than the county. Scope is one outline used three times
(Go API validation, the worker's guardrail, the map), so changing the region is mostly a question of which outline
decides scope and which sources and calibrations are valid inside it.

## Decision
- **Region = the 50 states + DC.** The outline comes from Census TIGERweb (`us_states_boundary` in
  `providers.yaml`, `kind: reference_layer`), unioned and simplified to ~500 m, committed as
  `apps/worker/config/regions/usa.geojson` (~280 KB) by `apps/worker/scripts/build_region_seed.py`.
  That file is the single source of truth; the script derives the other copies on request:
  - `--seed-out <path>` (S7): idempotent SQL loading it as `reference_layers` row `region`; Go checks requests
    with `ST_Within(area, region)`.
  - `--web-out <path>` (S1): the GeoJSON drawn on the map and used for a quick client-side check.
  - The worker's guardrail (`agent/guardrails.py`) reads the outline directly.
  Territories (PR, GU, VI, AS, MP) are out of scope for now.
- **Limits unchanged:** area ≤ 5,000 km², date range ≤ 3 years, error code `AREA_OUTSIDE_REGION`. No contract
  change for analyses.
- **`providers.yaml` areas:** `conus_bbox` (FIRMS and WFIGS default area), `alaska_bbox`, `hawaii_bbox`, `ca_bbox`;
  `sb_county_bbox` stays. County outlines for place names: `us_counties_boundary` →
  `config/regions/us_counties.geojson` (3,144 counties, ~2.6 MB).
- **Historical perimeters, one archive per area** (no double counting) — **S4 builds these**:

  | Area | Source | Coverage |
  |---|---|---|
  | inside California | `calfire_historical` (CAL FIRE FRAP, layer 2 of the historic service) | 1950 onward |
  | elsewhere | `wfigs_history` (NIFC WFIGS Interagency Perimeters, all years) | ~2016 onward |

  `wfigs_history` can subclass the `wfigs_current` reference (same host and fields, filtered by discovery date).
  `wfigs_current` already maps `incident_type` (wildfire / prescribed burn), so a prescribed burn is never reported
  as a wildfire. Reference implementations of both connectors and the routing (`perimeter_source()`) are on the
  demo branch.
- **Already national, nothing to do:** FIRMS and Sentinel-2 (global), NWS forecasts/alerts and WFIGS current (US).

## Consequences and limits
- **Antimeridian:** the Aleutians are split at ±180° (valid MultiPolygon); an area drawn *across* 180° is rejected.
- **Archive floor:** outside California, fires before ~2016 have no official perimeter; questions about them get the
  satellite evidence with an "insufficient official records" limitation. MTBS (1984+) is the next source.
- **Calibration (S6/S8):** dNBR thresholds are forest-calibrated (Key & Benson). Grassland, shrub-steppe, desert and
  tundra need per-ecoregion calibration before severity classes are trusted nationally; the limitation stays on every
  result. On the demo, three recorded fires (CA ×2, CO) agreed with official acreage within 17–25 % — a start, not an
  evaluation. S8's evaluation set should span ecoregions.
- **Offline fixtures** are mostly California; other states run live or return honest "insufficient evidence" until
  sections record more cases.
- **Load:** a national audience makes FIRMS key limits and caching (ADR-006, S7's ingest runner) matter sooner.
