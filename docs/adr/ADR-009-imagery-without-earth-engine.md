# ADR-009: Satellite imagery without Google Earth Engine (MVP)

## Status
Accepted (Sep 24, 2026). Amends [ADR-005](ADR-005-gee-tile-access.md). Deviates from spec §5, §11.1 and §14 (Earth Engine).

## Context
The spec computes vegetation change (NDVI) and burn severity (NBR/dNBR) from Sentinel-2 in Google Earth Engine. That needs a registered Cloud project, noncommercial eligibility review, IAM access for each teammate who works on it, a deployment service account and quota management. For a student team's MVP that setup cost comes before any value, and it blocks S6.

We checked the alternatives on Sep 24, 2026 against the 2024 **Line Fire** (43,976 acres, San Bernardino NF):

| Option | Checked result |
|---|---|
| **Earth Search** (Element 84) STAC API over **Sentinel-2 L2A on AWS open data** | Works with no account or key. The `sentinel-2-l2a` collection has `red`, `nir`, `nir08`, `swir22`, `scl` and `visual` assets as COGs. Anonymous HTTP range reads work (206). An Oct 9, 2024 scene of the fire area has 0.01% cloud. |
| **BAER Soil Burn Severity** (USFS, via GeoPlatform image service) | Real classes inside the Line Fire perimeter (Low/Moderate). Service time extent reaches 2025. Legend: Unburned to very low · Low · Moderate · High · Masked (developed). |
| **MTBS** burn severity (USFS/USGS, GeoPlatform image service) | A 2024 mosaic exists, but it returned **NoData** for the Line Fire: MTBS lags up to about a year. |
| **RAVG** (USFS, GeoPlatform mirror) | Yearly mosaics only up to 2023 on this mirror. |
| Google Earth Engine | Works, but needs the setup above. |

**End-to-end proof (Sep 24, 2026):** a working prototype computed Line Fire dNBR from Earth Search Sentinel-2 in ~16 s and matched the official BAER map within one class on 98.2% of the fire (98.5% once rebuilt on `kit/imagery.py`, whose exact grid aligns BAER precisely). See [docs/research/line-fire-2024](../research/line-fire-2024/README.md).

## Decision
1. **Measured imagery:** Sentinel-2 L2A via **Earth Search**, processed in the worker. We search for the least-cloudy scenes before and after, read only the AOI window from the COGs, mask with `scl`, and compute NDVI and NBR/dNBR with our own tested NumPy functions (S6).
   - The lead builds the reference for this new **STAC imagery** pattern, `kit/imagery.py`: search, scene choice, windowed reads, masking, and tracing through the kit's allowlisted HTTP.
2. **Official burn severity:** **BAER Soil Burn Severity** first, because it covers recent fires; **MTBS** as a second source when its data arrives. Both are ArcGIS image services, so S4 builds them by copying the ArcGIS reference connector. They are labelled as official assessments, separate from our own calculations.
3. **Display:** the worker renders raster results (NDVI change, dNBR classes, true colour) as **PNG overlays with bounds**, stored in object storage and served through the API. The `/v1/tiles/...` route from ADR-005 stays reserved for tiled output later (e.g. COG tiling), but it no longer proxies Earth Engine.
4. **Earth Engine moves to phase two.** It stays an option for large areas or datasets we can't get elsewhere (ECOSTRESS, GOES-19). The `gee-sentinel2.md` spec is kept for that.

## Alternatives considered
- **Keep Earth Engine:** most scalable and no raster code of our own, but the setup and access management come first. Deferred, not rejected.
- **Official maps only (BAER/MTBS/RAVG):** simplest, but no custom areas or dates, no NDVI, and coverage gaps (MTBS lag; BAER only for fires with a BAER assessment).
- **Microsoft Planetary Computer STAC:** similar to Earth Search. Not chosen: Earth Search needs no token signing and was verified working.
- **Copernicus Data Space / Sentinel Hub:** needs an account and has quota tiers.

## Consequences
- **Positive:** nobody needs imagery credentials. Works in the worker's Docker image anywhere. Official plus measured severity gives two independent evidence categories (spec §15 "corroborated").
- **Negative:** we own more raster code (masking, windowing, resampling 20 m SWIR to the 10 m grid, overlay rendering). Processing is bounded by worker CPU and memory, so AOI size limits (enforced by Go) matter more. New dependencies (`rasterio` and a STAC client) make the worker image larger.
- **Licensing:** Sentinel-2 data is from the Copernicus programme and needs attribution (e.g. *"Contains modified Copernicus Sentinel data 2024"*). TODO: link the exact Copernicus legal notice in `earth-search-s2.md`.
- **Spec correction found while checking:** the CAL FIRE URL in spec §11.4 (`2025_California_Fire_Perimeters_View`) holds **only 2025 fires**. Historical work must use `California_Historic_Fire_Perimeters` (layer 2, 1950–2025). See `docs/connectors/providers/calfire-historical.md`.

## Trade-offs
We trade Google's managed compute for independence from accounts and quotas. At county-scale AOIs the worker handles the processing easily. If AOIs or dataset needs grow, Earth Engine can be added as a second `compute` path without changing the evidence contract.
