"""Remove secret values from anything that might be logged, traced or saved as a fixture."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote, quote_plus

MASK = "***"


class Redactor:
    def __init__(self, secrets: Iterable[str | None]):
        values: set[str] = set()
        for s in secrets:
            if s and len(s) >= 4:  # very short values would mask ordinary text
                values.update({s, quote(s, safe=""), quote_plus(s)})
        # longest first so an encoded variant is never half-replaced
        self._secrets = sorted(values, key=len, reverse=True)

    def __bool__(self) -> bool:
        return bool(self._secrets)

    def text(self, value: str) -> str:
        for s in self._secrets:
            value = value.replace(s, MASK)
        return value

    def bytes(self, value: bytes) -> bytes:
        for s in self._secrets:
            value = value.replace(s.encode(), MASK.encode())
        return value

    def mapping(self, value: dict[str, str]) -> dict[str, str]:
        return {k: self.text(v) for k, v in value.items()}
