"""The only HTTP client allowed to talk to providers.

Guarantees: https only, host allowlist (including followed links), secrets injected from env and redacted
everywhere, hard timeout, streamed size cap, bounded retries on 429/5xx/timeouts, no redirects.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from inland_worker.kit.config import ProviderConfig
from inland_worker.kit.connector import ProviderRequest, RawResponse
from inland_worker.kit.errors import (
    HostNotAllowed,
    ProviderAuthMissing,
    ProviderError,
    ProviderHTTPError,
    ProviderRateLimited,
    ProviderResponseTooLarge,
    ProviderTimeout,
)
from inland_worker.kit.redact import Redactor


class KitHttpClient:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        env: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config
        self._env = os.environ if env is None else env
        self._transport = transport
        self.redactor = Redactor(self._env.get(name) for name in config.env_refs())

    # ------------------------------------------------------------------------------------------
    def _secret(self) -> str | None:
        auth = self.config.auth
        if auth.type == "none":
            return None
        value = self._env.get(auth.env or "")
        if not value:
            raise ProviderAuthMissing(
                self.config.provider_id, f"environment variable {auth.env} is not set (see .env.example)"
            )
        return value

    def prepare(self, req: ProviderRequest) -> tuple[str, dict[str, str], dict[str, str]]:
        """Return (url, params, headers) with auth applied. Raises HostNotAllowed before any I/O."""
        auth = self.config.auth
        secret = self._secret()
        url = req.url or self.config.base_url.rstrip("/") + req.path
        params = dict(req.params)
        headers = {**self.config.resolve_headers(self._env), **req.headers}
        placeholder = "{" + (auth.name or "") + "}"
        if auth.type == "path_placeholder":
            if placeholder not in url:
                raise ProviderAuthMissing(self.config.provider_id, f"request path is missing {placeholder}")
            url = url.replace(placeholder, secret or "")
        elif auth.type == "query_param":
            params[auth.name or ""] = secret or ""
        elif auth.type == "header":
            headers[auth.name or ""] = secret or ""
        self._check_host(url)
        return url, params, headers

    def _check_host(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.config.allowed_hosts:
            raise HostNotAllowed(
                self.config.provider_id,
                f"refusing to call {parsed.scheme}://{parsed.hostname} (allowed: {self.config.allowed_hosts})",
            )

    def redacted_url(self, url: str, params: Mapping[str, str]) -> str:
        full = f"{url}?{urlencode(params)}" if params else url
        return self.redactor.text(full)

    # ------------------------------------------------------------------------------------------
    async def get(self, req: ProviderRequest) -> RawResponse:
        url, params, headers = self.prepare(req)
        retry_cfg = self.config.retries
        retrying = AsyncRetrying(
            stop=stop_after_attempt(retry_cfg.max + 1),
            wait=wait_exponential(multiplier=retry_cfg.backoff_s, max=max(retry_cfg.backoff_s * 8, 0.001)),
            retry=retry_if_exception(lambda e: isinstance(e, ProviderError) and e.retryable),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._once(req, url, params, headers)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _once(
        self, req: ProviderRequest, url: str, params: dict[str, str], headers: dict[str, str]
    ) -> RawResponse:
        pid = self.config.provider_id
        safe_url = self.redacted_url(url, params)
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.config.timeout_s, follow_redirects=False, transport=self._transport
                ) as client,
                client.stream(req.method, url, params=params, headers=headers, json=req.json_body) as resp,
            ):
                status = resp.status_code
                if status == 429:
                    raise ProviderRateLimited(pid, f"rate limited by {urlparse(url).hostname}")
                if status >= 300:
                    raise ProviderHTTPError(
                        pid,
                        status,
                        f"{req.method} {safe_url}",
                        retryable=status in self.config.retries.on_status,
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > self.config.max_response_bytes:
                        raise ProviderResponseTooLarge(
                            pid, f"response exceeded {self.config.max_response_bytes} bytes"
                        )
                    chunks.append(chunk)
                return RawResponse(
                    request=req,
                    url=safe_url,
                    status=status,
                    content_type=resp.headers.get("content-type"),
                    body=b"".join(chunks),
                    retrieved_at=datetime.now(UTC),
                )
        except httpx.TimeoutException:
            # `from None`: the original httpx error can contain the unredacted URL
            raise ProviderTimeout(pid, f"timed out after {self.config.timeout_s}s") from None
        except httpx.TransportError as exc:
            # connection errors are transient; message is redacted because it can echo the URL
            raise ProviderHTTPError(
                pid, 0, self.redactor.text(str(exc)) or "transport error", retryable=True
            ) from None
