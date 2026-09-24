"""Record a live provider response as a test fixture (secrets are stripped before writing).

make record-fixture PROVIDER=wfigs_current CASE=success ARGS="--bbox -124.5,32.5,-114.1,42.0"
make record-fixture PROVIDER=firms CASE=success ARGS="--area sb_county_bbox --params '{\"days\": 5}'"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from inland_worker.connectors.registry import get_connector
from inland_worker.kit import FixtureStore, KitHttpClient, ProviderError, fetch, load_providers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("provider")
    ap.add_argument("case")
    ap.add_argument("--bbox", help="west,south,east,north")
    ap.add_argument("--area", help="named area from providers.yaml, e.g. sb_county_bbox")
    ap.add_argument("--point", help="lon,lat: records a tiny bbox around a point")
    ap.add_argument("--params", default="{}", help="connector params as JSON")
    ap.add_argument("--date-range", help="YYYY-MM-DD/YYYY-MM-DD")
    ap.add_argument("--note", default="")
    ap.add_argument("--force", action="store_true", help="overwrite an existing case")
    args = ap.parse_args()

    registry = load_providers()
    connector = get_connector(args.provider, registry)
    if args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split(","))
    elif args.point:
        lon, lat = (float(v) for v in args.point.split(","))
        bbox = (lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01)
    else:
        area = args.area or connector.config.ingestion.default_area
        if not area:
            ap.error("give --bbox, --point or --area")
        bbox = registry.area_bbox(area)
    date_range = None
    if args.date_range:
        start, end = args.date_range.split("/")
        date_range = {"start": start, "end": end}
    query = connector.query(bbox=bbox, date_range=date_range, params=json.loads(args.params))

    client = KitHttpClient(connector.config)
    try:
        result = asyncio.run(fetch(connector, query, mode="live", client=client))
    except ProviderError as exc:
        print(f"fetch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    store = FixtureStore()
    path = store.save(
        args.provider,
        args.case,
        result.responses,
        redactor=client.redactor,
        note=args.note,
        overwrite=args.force,
    )
    print(f"recorded {len(result.responses)} response(s), {len(result.items)} evidence item(s) → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
