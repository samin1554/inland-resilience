"""Connector kit: everything a connector needs, so connectors only build requests and parse responses."""

from inland_worker.kit.config import ProviderConfig, ProviderRegistry, load_providers
from inland_worker.kit.connector import (
    BaseConnector,
    BBox,
    NoParams,
    ProviderQuery,
    ProviderRequest,
    RawResponse,
)
from inland_worker.kit.errors import (
    ContractViolation,
    FixtureNotFound,
    HostNotAllowed,
    ProviderAuthMissing,
    ProviderConfigError,
    ProviderError,
    ProviderHTTPError,
    ProviderParseError,
    ProviderRateLimited,
    ProviderResponseTooLarge,
    ProviderTimeout,
)
from inland_worker.kit.fixtures import FixtureStore
from inland_worker.kit.http import KitHttpClient
from inland_worker.kit.runner import FetchResult, fetch

__all__ = [
    "BBox",
    "BaseConnector",
    "ContractViolation",
    "FetchResult",
    "FixtureNotFound",
    "FixtureStore",
    "HostNotAllowed",
    "KitHttpClient",
    "NoParams",
    "ProviderAuthMissing",
    "ProviderConfig",
    "ProviderConfigError",
    "ProviderError",
    "ProviderHTTPError",
    "ProviderParseError",
    "ProviderQuery",
    "ProviderRateLimited",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponseTooLarge",
    "ProviderTimeout",
    "RawResponse",
    "fetch",
    "load_providers",
]
