"""Recorded provider responses, so everything can run offline without API keys.

Layout:  tests/fixtures/<provider_id>/<case>/meta.json  +  one body file per response.
Standard cases: success, empty, malformed, extra_fields. Secrets are stripped when recording.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.errors import FixtureNotFound
from inland_worker.kit.redact import Redactor

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
STANDARD_CASES = ("success", "empty", "malformed", "extra_fields")

_EXT = {"json": "json", "geo+json": "json", "csv": "csv", "text": "txt"}


class FixtureResponse(BaseModel):
    label: str
    url: str
    status: int
    content_type: str | None
    body_file: str
    retrieved_at: datetime
    request: ProviderRequest


class FixtureMeta(BaseModel):
    provider_id: str
    case: str
    recorded_at: datetime
    origin: Literal["live", "derived", "synthetic"]
    note: str = ""
    responses: list[FixtureResponse]


def _ext(content_type: str | None) -> str:
    ct = (content_type or "").lower()
    for key, ext in _EXT.items():
        if key in ct:
            return ext
    return "bin"


class FixtureStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or os.environ.get("INLAND_FIXTURES_DIR") or DEFAULT_FIXTURES_DIR)

    def case_dir(self, provider_id: str, case: str) -> Path:
        return self.root / provider_id / case

    def exists(self, provider_id: str, case: str) -> bool:
        return (self.case_dir(provider_id, case) / "meta.json").exists()

    def cases(self, provider_id: str) -> list[str]:
        d = self.root / provider_id
        return sorted(p.name for p in d.iterdir() if (p / "meta.json").exists()) if d.exists() else []

    def load_meta(self, provider_id: str, case: str) -> FixtureMeta:
        path = self.case_dir(provider_id, case) / "meta.json"
        if not path.exists():
            raise FixtureNotFound(provider_id, f"no fixture case {case!r} at {path}")
        return FixtureMeta.model_validate_json(path.read_text())

    def load(self, provider_id: str, case: str) -> list[RawResponse]:
        meta = self.load_meta(provider_id, case)
        d = self.case_dir(provider_id, case)
        return [
            RawResponse(
                request=r.request,
                url=r.url,
                status=r.status,
                content_type=r.content_type,
                body=(d / r.body_file).read_bytes(),
                retrieved_at=r.retrieved_at,
            )
            for r in meta.responses
        ]

    def save(
        self,
        provider_id: str,
        case: str,
        responses: list[RawResponse],
        *,
        redactor: Redactor,
        origin: Literal["live", "derived", "synthetic"] = "live",
        note: str = "",
        overwrite: bool = False,
    ) -> Path:
        d = self.case_dir(provider_id, case)
        if (d / "meta.json").exists() and not overwrite:
            raise FileExistsError(f"{d} already exists; pass overwrite=True (--force) to replace it")
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():
            old.unlink()
        entries = []
        for i, r in enumerate(responses):
            body_file = f"{i:02d}_{r.request.label}.{_ext(r.content_type)}"
            (d / body_file).write_bytes(redactor.bytes(r.body))
            req = r.request.model_copy(
                update={
                    "url": redactor.text(r.request.url) if r.request.url else None,
                    "params": redactor.mapping(r.request.params),
                    "headers": {},  # never persist headers (User-Agent contacts, tokens)
                }
            )
            entries.append(
                FixtureResponse(
                    label=r.request.label,
                    url=redactor.text(r.url),
                    status=r.status,
                    content_type=r.content_type,
                    body_file=body_file,
                    retrieved_at=r.retrieved_at,
                    request=req,
                )
            )
        meta = FixtureMeta(
            provider_id=provider_id,
            case=case,
            recorded_at=datetime.now(UTC),
            origin=origin,
            note=note,
            responses=entries,
        )
        (d / "meta.json").write_text(json.dumps(meta.model_dump(mode="json"), indent=2) + "\n")
        return d
