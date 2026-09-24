"""Command line for the worker.

python -m inland_worker providers                       list configured data sources
python -m inland_worker fetch wfigs_current --bbox -124.5,32.5,-114.1,42.0
python -m inland_worker fetch firms --fixture           use recorded data (no keys, no network)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from inland_worker.connectors.registry import CONNECTORS
from inland_worker.data import DataService
from inland_worker.kit import load_providers


def _providers() -> int:
    reg = load_providers()
    for pid, cfg in reg.providers.items():
        status = "ready" if pid in CONNECTORS else "no connector yet"
        key = f"needs {cfg.auth.env}" if cfg.auth.env else "no key"
        print(f"{pid:<16} {cfg.ingestion.class_:<15} {key:<24} {status}  ({cfg.display_name})")
    return 0


def _fetch(args: argparse.Namespace) -> int:
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    date_range = None
    if args.date_range:
        start, end = args.date_range.split("/")
        date_range = {"start": start, "end": end}
    svc = DataService(mode="fixture" if args.fixture else None)
    try:
        result = asyncio.run(
            svc.get_evidence(args.provider, bbox=bbox, date_range=date_range, params=json.loads(args.params))
        )
    except (KeyError, ValueError) as exc:  # bad input: say what's wrong, no traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary = {
        "provider_id": result.provider_id,
        "origin": result.origin,
        "freshness": result.freshness.model_dump(),
        "count": len(result.items),
        "first": result.items[0].model_dump(mode="json") if result.items else None,
    }
    if summary["first"] and summary["first"]["geometry"]:
        summary["first"]["geometry"] = {"type": summary["first"]["geometry"]["type"], "coordinates": "…"}
    print(json.dumps(summary, indent=2, default=str))
    return 0 if result.ok else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="inland_worker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("providers", help="list configured data sources")
    f = sub.add_parser("fetch", help="get evidence from one provider and print a summary")
    f.add_argument("provider")
    f.add_argument("--bbox", help="west,south,east,north (default: the provider's default area)")
    f.add_argument("--date-range", help="YYYY-MM-DD/YYYY-MM-DD (needed by earth_search_s2)")
    f.add_argument("--params", default="{}", help="connector params as JSON")
    f.add_argument("--fixture", action="store_true", help="use recorded fixtures instead of the network")
    args = ap.parse_args(argv)
    return _providers() if args.cmd == "providers" else _fetch(args)


if __name__ == "__main__":
    sys.exit(main())
