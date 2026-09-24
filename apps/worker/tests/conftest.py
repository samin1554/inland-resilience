import pytest


@pytest.fixture(autouse=True)
def _offline_defaults(monkeypatch):
    """Tests never depend on the developer's real environment."""
    monkeypatch.delenv("INLAND_DATA_MODE", raising=False)
    monkeypatch.setenv("NWS_USER_AGENT", "inland-resilience-tests/0.1")
