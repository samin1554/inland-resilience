"""Derive the standard edge-case fixtures from a recorded `success` case.

malformed     the last response body cut in half (tests the parse-error path)
extra_fields  an unexpected field added everywhere (tests tolerance to schema drift)
empty         only if the provider can't easily be recorded empty live:
                --empty-csv                    keep only the CSV header
                --empty-json-path a.b.c        set that JSON path to [] in the last response

make derive-fixtures PROVIDER=nws_forecast ARGS="--empty-json-path properties.periods"
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from typing import Any

from inland_worker.kit import FixtureStore
from inland_worker.kit.redact import Redactor

EXTRA_KEY = "x_unexpected_field"


def _add_extra(value: Any) -> Any:
    if isinstance(value, dict):
        out = {k: _add_extra(v) for k, v in value.items()}
        out[EXTRA_KEY] = "added by derive_fixtures to test schema drift"
        return out
    if isinstance(value, list):
        return [_add_extra(v) for v in value]
    return value


def _extra_csv(text: str) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return text
    rows[0].append(EXTRA_KEY)
    for row in rows[1:]:
        row.append("x")
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("provider")
    ap.add_argument("--empty-csv", action="store_true")
    ap.add_argument("--empty-json-path")
    args = ap.parse_args()

    store = FixtureStore()
    base = store.load(args.provider, "success")
    no_secrets = Redactor([])
    is_csv = "csv" in (base[-1].content_type or "") or base[-1].request.expect == "text"

    last = base[-1]
    truncated = last.model_copy(update={"body": last.body[: max(1, len(last.body) // 2)]})
    store.save(
        args.provider,
        "malformed",
        [*base[:-1], truncated],
        redactor=no_secrets,
        origin="derived",
        note="success with the last body cut in half",
        overwrite=True,
    )

    if is_csv:
        extra = [r.model_copy(update={"body": _extra_csv(r.text()).encode()}) for r in base]
    else:
        extra = [r.model_copy(update={"body": json.dumps(_add_extra(r.json())).encode()}) for r in base]
    store.save(
        args.provider,
        "extra_fields",
        extra,
        redactor=no_secrets,
        origin="derived",
        note=f"success with '{EXTRA_KEY}' added everywhere",
        overwrite=True,
    )

    if args.empty_csv:
        header = last.text().splitlines()[0] + "\n"
        store.save(
            args.provider,
            "empty",
            [*base[:-1], last.model_copy(update={"body": header.encode()})],
            redactor=no_secrets,
            origin="derived",
            note="success reduced to the CSV header",
            overwrite=True,
        )
    elif args.empty_json_path:
        payload = last.json()
        node = payload
        *parents, leaf = args.empty_json_path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = []
        store.save(
            args.provider,
            "empty",
            [*base[:-1], last.model_copy(update={"body": json.dumps(payload).encode()})],
            redactor=no_secrets,
            origin="derived",
            note=f"success with {args.empty_json_path} = []",
            overwrite=True,
        )
    print(
        f"derived malformed, extra_fields{', empty' if args.empty_csv or args.empty_json_path else ''} "
        f"for {args.provider}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
