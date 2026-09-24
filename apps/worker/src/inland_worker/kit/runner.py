"""Run a connector: build requests → (fixtures | HTTP) → follow links/pages → parse → check the rules."""

from __future__ import annotations

import os
from collections import deque
from typing import Literal

from pydantic import BaseModel, ConfigDict

from inland_worker.contracts.models import Evidence
from inland_worker.kit.connector import BaseConnector, ProviderQuery, RawResponse
from inland_worker.kit.errors import ContractViolation, ProviderError, ProviderParseError
from inland_worker.kit.fixtures import FixtureStore
from inland_worker.kit.http import KitHttpClient

Mode = Literal["live", "fixture"]


def data_mode() -> Mode:
    return "fixture" if os.environ.get("INLAND_DATA_MODE", "live").lower() == "fixture" else "live"


class FetchResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[Evidence]
    responses: list[RawResponse]
    origin: Literal["live", "fixture"]


async def fetch(
    connector: BaseConnector,
    query: ProviderQuery,
    *,
    mode: Mode | None = None,
    case: str = "success",
    client: KitHttpClient | None = None,
    fixtures: FixtureStore | None = None,
) -> FetchResult:
    mode = mode or data_mode()
    pid = connector.provider_id
    if mode == "fixture":
        responses = (fixtures or FixtureStore()).load(pid, case)
    else:
        client = client or KitHttpClient(connector.config)
        responses = []
        queue = deque(connector.build_requests(query))
        follows = 0
        while queue:
            resp = await client.get(queue.popleft())
            responses.append(resp)
            nxt = connector.follow(resp, query)
            follows += len(nxt)
            if follows > connector.config.max_follow:
                raise ProviderError(pid, f"more than {connector.config.max_follow} follow-up requests")
            queue.extend(nxt)
    try:
        items = connector.parse(responses, query)
    except ProviderError:
        raise
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise ProviderParseError(pid, f"could not parse response: {type(exc).__name__}: {exc}") from exc
    check_items(connector, items)
    return FetchResult(items=items, responses=responses, origin=mode)


def check_items(connector: BaseConnector, items: list[Evidence]) -> None:
    """Enforce the evidence rules every connector must follow (connector guide §3.2)."""
    pid = connector.provider_id
    allowed = set(connector.evidence_types) & set(connector.config.evidence_types)
    for item in items:
        if item.evidence_type not in allowed:
            raise ContractViolation(pid, f"emitted {item.evidence_type} but may only emit {sorted(allowed)}")
        if item.evidence_type == "agent_inference":
            raise ContractViolation(pid, "connectors must never emit agent_inference")
        missing = [lim for lim in connector.config.default_limitations if lim not in item.limitations]
        if missing:
            raise ContractViolation(pid, f"item {item.id} is missing default limitations {missing}")
