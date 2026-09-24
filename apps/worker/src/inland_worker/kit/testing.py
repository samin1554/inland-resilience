"""The shared connector test suite (spec §21 checklist). Every connector test file subclasses it:

    class TestFirms(ConnectorContract):
        connector_cls = FirmsConnector
        query_kwargs = {"bbox": (-117.8, 33.8, -114.1, 35.9)}

and gets all of these tests for free. Add provider-specific tests in the same class.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
import respx
from jsonschema import Draft202012Validator

from inland_worker.kit.config import load_providers
from inland_worker.kit.connector import BaseConnector, ProviderQuery
from inland_worker.kit.errors import ProviderParseError, ProviderRateLimited, ProviderTimeout
from inland_worker.kit.fixtures import FixtureStore
from inland_worker.kit.http import KitHttpClient
from inland_worker.kit.runner import FetchResult, fetch

CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "contracts"


@lru_cache(maxsize=1)
def evidence_validator() -> Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / "evidence.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def assert_valid_evidence(items: list[Any]) -> None:
    validator = evidence_validator()
    for item in items:
        errors = sorted(validator.iter_errors(item.model_dump(mode="json")), key=str)
        assert not errors, f"evidence {item.id} breaks evidence.schema.json: {errors[0].message}"


class ConnectorContract:
    connector_cls: ClassVar[type[BaseConnector]]
    query_kwargs: ClassVar[dict[str, Any]] = {"bbox": (-117.8, 33.8, -114.1, 35.9)}

    # --- helpers ---------------------------------------------------------------------------------
    def connector(self) -> BaseConnector:
        registry = load_providers()
        pid = self.connector_cls.provider_id
        if pid not in registry.providers:
            pytest.fail(f"add a `{pid}:` block to apps/worker/config/providers.yaml (copy a reference block)")
        cfg = registry.get(pid).model_copy(deep=True)
        cfg.retries.backoff_s = 0  # keep retry tests fast
        cfg.retries.max = 2
        return self.connector_cls(cfg)

    def query(self, connector: BaseConnector) -> ProviderQuery:
        return connector.query(**self.query_kwargs)

    def fake_env(self, connector: BaseConnector) -> dict[str, str]:
        return {name: f"test-secret-{name}-7f3a9c" for name in connector.config.env_refs()}

    async def run_fixture(self, case: str) -> FetchResult:
        c = self.connector()
        return await fetch(c, self.query(c), mode="fixture", case=case)

    # --- the suite -------------------------------------------------------------------------------
    def test_fixtures_exist(self) -> None:
        store = FixtureStore()
        missing = [
            c
            for c in ("success", "empty", "malformed", "extra_fields")
            if not store.exists(self.connector_cls.provider_id, c)
        ]
        assert not missing, f"record fixtures first: {missing} (see connector guide §5)"

    async def test_success(self) -> None:
        result = await self.run_fixture("success")
        assert result.items, "the success fixture should produce at least one evidence item"
        assert_valid_evidence(result.items)

    async def test_empty_returns_empty_list(self) -> None:
        result = await self.run_fixture("empty")
        assert result.items == []

    async def test_malformed_fails_cleanly(self) -> None:
        try:
            result = await self.run_fixture("malformed")
        except ProviderParseError:
            return
        assert_valid_evidence(result.items)  # tolerated only if what came out is still valid

    async def test_schema_drift_is_ignored(self) -> None:
        base = (await self.run_fixture("success")).items
        drift = (await self.run_fixture("extra_fields")).items
        assert [i.id for i in drift] == [i.id for i in base]
        assert [set(i.properties) for i in drift] == [set(i.properties) for i in base]

    async def test_timestamps(self) -> None:
        for item in (await self.run_fixture("success")).items:
            assert item.observed_at.tzinfo is not None and item.retrieved_at.tzinfo is not None
            assert item.observed_at <= item.retrieved_at, f"{item.id}: observed after it was retrieved"

    async def test_limitations_and_source(self) -> None:
        c = self.connector()
        for item in (await self.run_fixture("success")).items:
            for lim in c.config.default_limitations:
                assert lim in item.limitations
            assert item.source == c.config.display_name
            assert item.source_url == c.config.source_url

    async def test_timeout_is_retried_then_raised(self) -> None:
        c = self.connector()
        with respx.mock(assert_all_called=False) as router:
            route = router.route().mock(side_effect=httpx.ReadTimeout("slow"))
            with pytest.raises(ProviderTimeout):
                await fetch(
                    c, self.query(c), mode="live", client=KitHttpClient(c.config, env=self.fake_env(c))
                )
            assert route.call_count == c.config.retries.max + 1

    async def test_rate_limit_is_retried_then_raised(self) -> None:
        c = self.connector()
        with respx.mock(assert_all_called=False) as router:
            route = router.route().mock(return_value=httpx.Response(429))
            with pytest.raises(ProviderRateLimited):
                await fetch(
                    c, self.query(c), mode="live", client=KitHttpClient(c.config, env=self.fake_env(c))
                )
            assert route.call_count == c.config.retries.max + 1

    async def test_live_path_replays_and_leaks_no_secrets(self) -> None:
        """Run the real HTTP path against recorded bodies: auth is applied, follow-ups work, secrets never leak."""
        c = self.connector()
        env = self.fake_env(c)
        recorded = FixtureStore().load(c.provider_id, "success")
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(
                side_effect=[
                    httpx.Response(r.status, content=r.body, headers={"content-type": r.content_type or ""})
                    for r in recorded
                ]
            )
            result = await fetch(c, self.query(c), mode="live", client=KitHttpClient(c.config, env=env))
            sent = [call.request for call in router.calls]
        assert len(result.items) == len((await self.run_fixture("success")).items)
        dump = json.dumps([i.model_dump(mode="json") for i in result.items]) + " ".join(
            r.url for r in result.responses
        )
        for secret in env.values():
            assert secret not in dump, "a secret leaked into evidence or a recorded URL"
        if c.config.auth.type != "none":
            wire = " ".join(str(req.url) + " " + " ".join(req.headers.values()) for req in sent)
            assert env[c.config.auth.env] in wire, "the kit did not apply the provider's auth"
