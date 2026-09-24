"""Typed errors raised by the connector kit. Messages never contain secret values."""


class ProviderError(Exception):
    """Base class. `code` is stable and goes into traces and job error codes."""

    code = "PROVIDER_ERROR"
    retryable = False

    def __init__(self, provider_id: str, message: str):
        self.provider_id = provider_id
        super().__init__(f"[{provider_id}] {message}")


class ProviderConfigError(ProviderError):
    code = "PROVIDER_CONFIG_ERROR"


class ProviderAuthMissing(ProviderConfigError):
    code = "PROVIDER_AUTH_MISSING"


class HostNotAllowed(ProviderError):
    code = "HOST_NOT_ALLOWED"


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"
    retryable = True


class ProviderRateLimited(ProviderError):
    code = "PROVIDER_RATE_LIMITED"
    retryable = True


class ProviderHTTPError(ProviderError):
    code = "PROVIDER_HTTP_ERROR"

    def __init__(self, provider_id: str, status: int, message: str, retryable: bool = False):
        self.status = status
        self.retryable = retryable
        super().__init__(provider_id, f"HTTP {status}: {message}")


class ProviderResponseTooLarge(ProviderError):
    code = "PROVIDER_RESPONSE_TOO_LARGE"


class ProviderParseError(ProviderError):
    code = "PROVIDER_PARSE_ERROR"


class ContractViolation(ProviderError):
    """A connector produced evidence that breaks the rules (wrong type, missing timestamps or limitations)."""

    code = "CONTRACT_VIOLATION"


class FixtureNotFound(ProviderError):
    code = "FIXTURE_NOT_FOUND"
