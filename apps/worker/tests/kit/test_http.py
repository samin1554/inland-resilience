import httpx
import pytest
import respx

from inland_worker.kit import (
    HostNotAllowed,
    KitHttpClient,
    ProviderAuthMissing,
    ProviderHTTPError,
    ProviderRequest,
    ProviderResponseTooLarge,
)
from inland_worker.kit.config import ProviderConfig

SECRET = "sk-test-0123456789abcdef"


def cfg(**over) -> ProviderConfig:
    base = dict(
        provider_id="p",
        display_name="P",
        base_url="https://api.example.com/v1",
        allowed_hosts=["api.example.com"],
        ingestion={"class": "on_demand"},
        source_url="https://example.com",
        retries={"max": 1, "backoff_s": 0},
    )
    return ProviderConfig(**{**base, **over})


@pytest.mark.parametrize(
    ("auth", "where"),
    [
        ({"type": "query_param", "env": "K", "name": "appKey"}, "query"),
        ({"type": "header", "env": "K", "name": "X-Api-Key"}, "header"),
        ({"type": "path_placeholder", "env": "K", "name": "MAP_KEY"}, "path"),
    ],
)
async def test_auth_is_applied_and_redacted(auth, where):
    c = KitHttpClient(cfg(auth=auth), env={"K": SECRET})
    path = "/{MAP_KEY}/data" if where == "path" else "/data"
    with respx.mock() as router:
        router.route().mock(return_value=httpx.Response(200, json={"ok": True}))
        resp = await c.get(ProviderRequest(path=path))
        sent = router.calls[0].request
    wire = str(sent.url) + " ".join(sent.headers.values())
    assert SECRET in wire
    assert SECRET not in resp.url
    if where != "header":  # header secrets never appear in the URL at all
        assert "***" in resp.url


async def test_missing_secret_is_a_clear_error_naming_only_the_variable():
    c = KitHttpClient(cfg(auth={"type": "query_param", "env": "MY_KEY", "name": "k"}), env={})
    with pytest.raises(ProviderAuthMissing, match="MY_KEY"):
        await c.get(ProviderRequest(path="/x"))


async def test_absolute_url_on_other_host_refused_without_io():
    c = KitHttpClient(cfg(), env={})
    with respx.mock(assert_all_called=False) as router:
        route = router.route().mock(return_value=httpx.Response(200))
        with pytest.raises(HostNotAllowed):
            await c.get(ProviderRequest(url="https://evil.example.org/x"))
        assert not route.called


async def test_plain_http_url_refused():
    c = KitHttpClient(cfg(), env={})
    with pytest.raises(HostNotAllowed):
        await c.get(ProviderRequest(url="http://api.example.com/x"))


async def test_response_size_cap():
    c = KitHttpClient(cfg(max_response_bytes=100), env={})
    with respx.mock() as router:
        router.route().mock(return_value=httpx.Response(200, content=b"x" * 1000))
        with pytest.raises(ProviderResponseTooLarge):
            await c.get(ProviderRequest(path="/big"))


async def test_5xx_retried_then_succeeds():
    c = KitHttpClient(cfg(), env={})
    with respx.mock() as router:
        route = router.route().mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
        resp = await c.get(ProviderRequest(path="/flaky"))
    assert resp.json() == {"ok": 1} and route.call_count == 2


async def test_4xx_not_retried():
    c = KitHttpClient(cfg(), env={})
    with respx.mock() as router:
        route = router.route().mock(return_value=httpx.Response(404))
        with pytest.raises(ProviderHTTPError) as exc:
            await c.get(ProviderRequest(path="/missing"))
    assert exc.value.status == 404 and route.call_count == 1


async def test_redirects_are_not_followed():
    c = KitHttpClient(cfg(), env={})
    with respx.mock() as router:
        router.route().mock(
            return_value=httpx.Response(302, headers={"location": "https://evil.example.org/"})
        )
        with pytest.raises(ProviderHTTPError):
            await c.get(ProviderRequest(path="/redir"))


async def test_error_messages_never_contain_the_secret():
    c = KitHttpClient(cfg(auth={"type": "query_param", "env": "K", "name": "key"}), env={"K": SECRET})
    with respx.mock() as router:
        router.route().mock(return_value=httpx.Response(400))
        with pytest.raises(ProviderHTTPError) as exc:
            await c.get(ProviderRequest(path="/x"))
    assert SECRET not in str(exc.value)
