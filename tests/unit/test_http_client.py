import pytest
import requests

from src.adapters.base import AdapterError, AdapterPermissionError, AdapterTimeout
from src.adapters.http import SafeHttpClient


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_http_error_redacts_credentials():
    session = FakeSession([requests.ConnectionError("token=secret-value")])
    client = SafeHttpClient(session, timeout=1, max_retries=0)

    with pytest.raises(AdapterError) as error:
        client.get("https://example.invalid", params={"token": "secret-value"})

    assert "secret-value" not in str(error.value)


def test_http_retries_timeout_then_succeeds():
    session = FakeSession([requests.Timeout("slow"), FakeResponse(200)])
    client = SafeHttpClient(session, timeout=1, max_retries=1)

    assert client.get("https://example.invalid").status_code == 200
    assert len(session.calls) == 2


def test_http_permission_error_does_not_retry():
    session = FakeSession([FakeResponse(403), FakeResponse(200)])
    client = SafeHttpClient(session, timeout=1, max_retries=1, source="tushare", dataset="daily")

    with pytest.raises(AdapterPermissionError):
        client.get("https://example.invalid")

    assert len(session.calls) == 1


def test_http_timeout_raises_adapter_timeout_after_retries():
    session = FakeSession([requests.Timeout("slow"), requests.Timeout("still slow")])
    client = SafeHttpClient(session, timeout=1, max_retries=1, source="tushare", dataset="daily")

    with pytest.raises(AdapterTimeout):
        client.get("https://example.invalid")
