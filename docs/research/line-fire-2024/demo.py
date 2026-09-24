"""Line Fire 2024: our dNBR from Sentinel-2 (Earth Search) vs official BAER soil burn severity."""
import json, time, urllib.parse, urllib.request
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from pyproj import Transformer
from pystac_client import Client
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

t0 = time.time()
DST_CRS, RES = "EPSG:32611", 20.0
fire_ll = make_valid(shape(json.load(open("line_fire.geojson"))["features"][0]["geometry"]))
to_utm = Transformer.from_crs("EPSG:4326", DST_CRS, always_xy=True).transform
fire = shp_transform(to_utm, fire_ll)
minx, miny, maxx, maxy = fire.buffer(600).bounds
W, H = int((maxx - minx) // RES), int((maxy - miny) // RES)
TRANSFORM = from_origin(minx, maxy, RES, RES)
inside = ~geometry_mask([mapping(fire)], out_shape=(H, W), transform=TRANSFORM)

cat = Client.open("https://earth-search.aws.element84.com/v1")
def items_on(date):
    return list(cat.search(collections=["sentinel-2-l2a"], bbox=fire_ll.bounds, datetime=date).items())

def read_band(items, asset, resampling, reflectance=True):
    """Reflectance per item: apply the BOA offset only if Earth Search has NOT already applied it."""
    out = np.full((H, W), np.nan, dtype=np.float32)
    for it in items:
        tmp = np.zeros((H, W), dtype=np.float32)
        with rasterio.open(it.assets[asset].href) as src:
            reproject(rasterio.band(src, 1), tmp, dst_transform=TRANSFORM, dst_crs=DST_CRS,
                      resampling=resampling, src_nodata=0, dst_nodata=0)
        tmp = np.where(tmp == 0, np.nan, tmp)
        if reflectance:
            rb = it.assets[asset].extra_fields["raster:bands"][0]
            offset = 0.0 if it.properties.get("earthsearch:boa_offset_applied") else rb["offset"]
            tmp = tmp * rb["scale"] + offset
        out = np.where(np.isnan(out), tmp, out)
    return out

def read_rgb(items):
    out = np.zeros((3, H, W), dtype=np.uint8)
    for it in items:
        with rasterio.open(it.assets["visual"].href) as src:
            tmp = np.zeros((3, H, W), dtype=np.uint8)
            for b in range(3):
                reproject(rasterio.band(src, b + 1), tmp[b], dst_transform=TRANSFORM, dst_crs=DST_CRS,
                          resampling=Resampling.average, src_nodata=0, dst_nodata=0)
        out = np.where(out == 0, tmp, out)
    return out

BAD_SCL = [0, 1, 3, 8, 9, 10]  # no data, saturated, cloud shadow, cloud medium/high, thin cirrus
def nbr_for(date):
    its = [i for i in items_on(date) if i.id.endswith("_0_L2A")]  # one processing version per tile
    nir = read_band(its, "nir", Resampling.average)
    swir = read_band(its, "swir22", Resampling.bilinear)
    scl = read_band(its, "scl", Resampling.nearest, reflectance=False)
    valid = np.isfinite(nir) & np.isfinite(swir) & ~np.isin(np.nan_to_num(scl), BAD_SCL) & (nir + swir > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        nbr = np.where(valid, (nir - swir) / (nir + swir), np.nan)
    return nbr, [i.id for i in its], read_rgb(its), valid

with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MULTIRANGE="YES", VSI_CACHE="TRUE"):
    nbr_pre, ids_pre, rgb_pre, v_pre = nbr_for("2024-08-20")
    nbr_post, ids_post, rgb_post, v_post = nbr_for("2024-10-19")
dnbr = nbr_pre - nbr_post

# USGS/Key & Benson (2006) dNBR thresholds, collapsed to BAER's 4 classes
edges = [0.10, 0.27, 0.66]           # <0.10 unburned/very low · low · moderate · high
ours = np.digitize(dnbr, edges) + 1  # 1..4
ours = np.where(np.isnan(dnbr), 0, ours)

# Official BAER soil burn severity on the same grid (ArcGIS exportImage as GeoTIFF)
B = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_BAER_SoilBurnSeverityClassification/ImageServer/exportImage"
q = urllib.parse.urlencode({"bbox": f"{minx},{miny},{maxx},{maxy}", "bboxSR": 32611, "imageSR": 32611,
                            "size": f"{W},{H}", "format": "tiff", "pixelType": "U8", "interpolation": "RSP_NearestNeighbor",
                            "mosaicRule": json.dumps({"mosaicMethod": "esriMosaicAttribute", "where": "beginyear<=2024 AND endyear>=2024"}),
                            "f": "image"})
import subprocess; subprocess.run(["curl", "-sf", "-m", "120", "-o", "baer.tif", f"{B}?{q}"], check=True)
with rasterio.open("baer.tif") as src:
    baer = src.read(1)
baer = np.where((baer >= 1) & (baer <= 4), baer, 0)

px_acres = RES * RES / 4046.8564224
names = ["Unburned/very low", "Low", "Moderate", "High"]
m_ours = inside & (ours > 0)
m_both = m_ours & (baer > 0)
res = {
    "fire": "LINE 2024 (CAL FIRE historic perimeters)", "perimeter_acres_calfire": 43975.61,
    "perimeter_acres_grid": round(inside.sum() * px_acres),
    "scenes_before": ids_pre, "scenes_after": ids_post,
    "valid_pixel_pct_inside": round(100 * m_ours.sum() / inside.sum(), 1),
    "dnbr_inside_p25_median_p75": [round(float(v), 3) for v in np.nanpercentile(np.where(inside, dnbr, np.nan), [25, 50, 75])],
    "dnbr_outside_median": round(float(np.nanmedian(np.where(~inside, dnbr, np.nan))), 3),
    "offset_rule": "offset applied only where earthsearch:boa_offset_applied is false",
    "ours_acres": {n: round(((ours == i + 1) & inside).sum() * px_acres) for i, n in enumerate(names)},
    "baer_acres": {n: round(((baer == i + 1) & inside).sum() * px_acres) for i, n in enumerate(names)},
    "baer_coverage_pct_inside": round(100 * (inside & (baer > 0)).sum() / inside.sum(), 1),
    "exact_class_agreement_pct": round(100 * ((ours == baer) & m_both).sum() / max(m_both.sum(), 1), 1),
    "within_one_class_pct": round(100 * ((np.abs(ours.astype(int) - baer.astype(int)) <= 1) & m_both).sum() / max(m_both.sum(), 1), 1),
    "seconds": round(time.time() - t0, 1),
}
json.dump(res, open("results.json", "w"), indent=2)
np.savez_compressed("arrays.npz", dnbr=dnbr, ours=ours, baer=baer, inside=inside, rgb_pre=rgb_pre, rgb_post=rgb_post)
print(json.dumps(res, indent=2))
