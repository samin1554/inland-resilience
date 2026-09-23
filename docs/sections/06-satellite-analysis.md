# Section 6: Satellite analysis

**Stack:** Python 3.12, Earth Engine Python API, NumPy, (Rasterio/Xarray if needed), pytest · **Pairs with:** S2

## Scope
Earth Engine auth (service account), Sentinel-2 scene discovery, SCL cloud/shadow masking, true colour, NDVI change, NBR/dNBR, summary statistics, tile-layer metadata. Deterministic functions only; the agent calls them as tools. See [gee-sentinel2.md](../connectors/providers/gee-sentinel2.md).

## Owned paths
`apps/worker/src/inland_worker/satellite/**` · `apps/worker/tests/satellite/**` · `docs/connectors/providers/gee-sentinel2.md`

## First tickets

**S6-1 Formula unit tests.** NDVI, NBR and dNBR over fixed NumPy arrays, including no-data and masked pixels. *Acceptance:* known values within 1e-6; masked pixels excluded from means.

**S6-2 Earth Engine auth + scene discovery.** *Input:* polygon, date window, cloud limit. *Output:* scenes with acquisition date and cloud %. *Failure test:* no scene under the cloud limit → `Missing` with a reason, never an empty success.

**S6-3 NDVI before/after** (spec §16/§17 good ticket). *Input:* two date windows + polygon. *Output:* least-cloudy valid composite per window; mean NDVI before, after, % change; acquisition dates; valid-pixel %; resolution; units. *Acceptance:* a repeatable result for one fixed historical San Bernardino fire, saved as the `compute` fixture.

**S6-4 dNBR burn severity** with class areas computed in an appropriate projected CRS (spec §21), then compared with the CAL FIRE perimeter area (feeds S8's metric).
