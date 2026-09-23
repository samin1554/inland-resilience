# Section 6: Satellite analysis

**Stack:** Python 3.12 · Google Earth Engine Python API · NumPy · pytest (Rasterio/Xarray only if needed)
**Pair partner:** Section 2 (analysis UI): your numbers become charts and evidence cards people can understand.
**Read first:** [Start here](../guides/start-here.md) · [Earth Engine provider spec](../connectors/providers/gee-sentinel2.md) · [Learning with AI](../guides/learning-with-ai.md) · [Coding with OpenCode](../guides/coding-with-opencode.md)

---

## 1. Your job in plain English

You do **the science**. You use satellite images to measure how the land changed: how much vegetation was lost, and how badly an area burned.

The European Sentinel-2 satellites photograph the Earth every few days in many "colours" (bands), including infrared that our eyes can't see. Healthy plants reflect lots of near-infrared light; burned ground doesn't. By comparing images from **before** and **after** a fire, we can calculate:
- **NDVI** (vegetation index): how green and healthy the vegetation is.
- **NBR / dNBR** (burn ratio and its change): how severely an area burned.

Google Earth Engine stores these images and does the heavy computing on Google's servers. We only send it instructions and get back numbers, small images and map tiles.

**Analogy:** you're a doctor comparing an X-ray from before and after an injury. You pick clear images (no clouds, like no motion blur), measure the same spot the same way both times, and report your numbers with how confident the measurement is.

![Agent workflow](../diagrams/agent-workflow.svg)

**Done looks like:** given an area and two date windows, your functions return before/after values, the change, the dates used, cloud coverage and units, repeatably. The same historical fire gives the same numbers every time.

## 2. What you own

| You own | Don't touch |
|---|---|
| `apps/worker/src/inland_worker/satellite/**` | `kit/**`, `data/**`, `agent/**` (lead) |
| `apps/worker/tests/satellite/**` | `contracts/**` (lead) |
| `docs/connectors/providers/gee-sentinel2.md` | connectors (S4/S5), evidence rules (S8) |

The agent calls your functions as **tools**. The AI model never does the math; your code does.

## 3. Key ideas before you start

| Term | Plain-English meaning |
|---|---|
| **Band** | One "colour" channel. We use B4 (red), B8 (near-infrared), B11/B12 (short-wave infrared) and SCL (scene classification). |
| **Surface reflectance** | Brightness corrected for the atmosphere. `COPERNICUS/S2_SR_HARMONIZED` is already corrected. |
| **NDVI** | (NIR − Red) / (NIR + Red) = (B8 − B4)/(B8 + B4). Ranges −1 to 1; higher = greener. |
| **NBR** | (NIR − SWIR2) / (NIR + SWIR2) = (B8 − B12)/(B8 + B12). |
| **dNBR** | NBR_before − NBR_after. Bigger = more severe burn. |
| **Cloud mask** | Removing pixels that are cloud, cloud shadow or missing (using SCL) **before** computing averages. |
| **Composite** | Combining several images from a date window into one (e.g. the least cloudy, or the median). |
| **Resolution** | Pixel size: 10 m for B4/B8, 20 m for B11/B12. Always reported with results. |
| **Projected CRS** | To measure *areas* in m² or acres, you need a projection in metres, not lat/long degrees. |
| **Deterministic** | Same inputs → same outputs. Fixed dates, fixed area, fixed method. |

## 4. Learn the stack (week 0)

| Tool | Why | Official docs | Practice exercise |
|---|---|---|---|
| NumPy | Array math for tests | [numpy.org/doc: absolute beginners](https://numpy.org/doc/stable/user/absolute_beginners.html) | Compute NDVI on two 3×3 arrays, handling divide-by-zero. |
| Earth Engine concepts | How GEE thinks (server-side objects) | [Earth Engine guides](https://developers.google.com/earth-engine/guides) | Read "Get started" and "Client vs. server". |
| Earth Engine Python API | Our interface | [Python installation](https://developers.google.com/earth-engine/guides/python_install) · [Authentication](https://developers.google.com/earth-engine/guides/auth) | Authenticate and print the size of a Sentinel-2 collection filtered to San Bernardino. |
| Sentinel-2 SR dataset | The data | [Dataset catalog page](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) | Find the SCL class values for cloud and shadow on this page. |
| Burn severity background | The science | [USGS: Landsat Normalized Burn Ratio](https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio) | Explain dNBR thresholds in your own words. |
| pytest | Tests | [docs.pytest.org](https://docs.pytest.org/en/stable/getting-started.html) | Test your NumPy NDVI function with known values. |

**Learn it with AI:**
```text
Explain Google Earth Engine's client vs server model to a Python programmer: why ee.Image objects
are "recipes" computed on Google's servers, what .getInfo() does, and why calling it in a loop is
slow. Use a Sentinel-2 NDVI example over a small polygon.
```

## 5. Set up your machine

```bash
pip install earthengine-api      # or: uv add earthengine-api (inside the worker project)
earthengine authenticate         # personal login for development
```
You need access to an Earth Engine–enabled Google Cloud project. The lead provides the project ID (`GEE_PROJECT_ID`) and, later, the service account used in deployment. Never commit credential files.

## 6. Build it step by step

### S6-1 Formula functions + unit tests (no Earth Engine yet)
- **Goal:** NDVI, NBR and dNBR are correct and tested.
- **Steps:** write NumPy versions of the formulas with masking (NaN for masked/no-data pixels); means ignore masked pixels.
- **AI prompt:**
  ```text
  Plan NumPy functions ndvi(nir, red), nbr(nir, swir2), dnbr(nbr_before, nbr_after) with masking
  support in apps/worker/src/inland_worker/satellite, plus pytest cases with hand-computed values,
  divide-by-zero, and fully masked arrays. Tests first.
  ```
- **Done when:** tests pass with values correct to 1e-6. These tests are our ground truth for checking the Earth Engine version.

### S6-2 Earth Engine auth + scene discovery
- **Goal:** find usable images for an area and date window.
- **Steps:** filter the collection by polygon + dates; compute the cloud percentage within the polygon using SCL; return a list of scenes with acquisition date and cloud %.
- **Failure case:** no scene under the cloud limit → return `Missing` with a reason ("no scene under 20% cloud between X and Y"), **never** an empty success.
- **Tests:** a recorded result JSON for one known area + window.

### S6-3 NDVI before/after (the spec's example ticket)
- **Goal:** two date windows + polygon → mean NDVI before, after and % change, plus acquisition dates, valid-pixel %, resolution and units.
- **Steps:** least-cloudy valid composite per window → mask → NDVI → `reduceRegion(mean)` at the right scale → package as `deterministic_calculation` evidence with the method and inputs recorded.
- **AI prompt:**
  ```text
  Plan calculate_ndvi_change(before_window, after_window, area) using Earth Engine and
  COPERNICUS/S2_SR_HARMONIZED. Mask with SCL before reducing, use an explicit scale, and return
  values, dates, valid_pixel_pct, resolution and units. Explain every Earth Engine call and
  where .getInfo() happens. Show how we make the result repeatable.
  ```
- **Check yourself:** run it twice on the same historical fire and get the same numbers; compare with your NumPy version on a tiny area.
- **Done when:** the result for one fixed historical San Bernardino fire is saved as the fixture.

### S6-4 dNBR burn severity
- **Goal:** dNBR statistics and burned-area estimates by severity class.
- **Steps:** as S6-3 but with NBR; compute areas in a **projected** CRS; include the class thresholds used.
- **Hand-off:** S8 compares your burned area with the official CAL FIRE perimeter.

### S6-5 Map layers (Milestone 3)
Produce tile-layer metadata (true colour, NDVI change, dNBR) and small before/after thumbnails for reports. Go serves the tiles ([ADR-005](../adr/ADR-005-gee-tile-access.md)).

**Common mistakes:** averaging before masking clouds; mixing the 10 m and 20 m bands without stating the scale; computing areas in degrees; calling `.getInfo()` inside loops; reporting a number without dates or units.

## 7. How your work connects

| You need | From | Until ready |
|---|---|---|
| Kit `compute` path + evidence schema | Lead | Plain functions returning dicts shaped like evidence |
| GEE project access | Lead | Your personal authenticated setup |
| Historical perimeter for test cases | S4 | The CAL FIRE query in a browser |

| Others need from you | Who |
|---|---|
| Numbers + units + dates for charts | S2 |
| Burn area for agreement metrics | S8 |
| Tools the agent can call | Lead |

## 8. When you're stuck

Earth Engine docs and the dataset page → OpenCode Plan mode (ask it to explain the client/server behaviour) → S2 (your pair) for presentation → the lead for project access → team chat with the snippet, the error and the area/dates used.

## 9. Coming from the lead

- [ ] GEE project ID + service-account setup for the worker
- [ ] Kit `compute` wrapper (timeouts, tracing, caching) you'll call through
- [ ] The chosen historical test fire(s) and date windows
- [ ] Cloud-limit and minimum valid-pixel thresholds
