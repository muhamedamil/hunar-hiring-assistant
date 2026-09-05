from __future__ import annotations

import httpx
import pytest

from app.core.http_client import ProviderHttpClient
from app.core.retry import (
    ProviderAuthenticationError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
)


def _client(response: httpx.Response) -> ProviderHttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    return ProviderHttpClient(
        base_url="https://provider.example",
        transport=httpx.MockTransport(handler),
    )


def test_401_is_authentication_error() -> None:
    with (
        _client(httpx.Response(401, json={"error": "bad key"})) as client,
        pytest.raises(ProviderAuthenticationError),
    ):
        client.request("GET", "/resource")


def test_429_carries_retry_after() -> None:
    with (
        _client(httpx.Response(429, headers={"Retry-After": "7"})) as client,
        pytest.raises(ProviderRateLimitError) as captured,
    ):
        client.request("GET", "/resource")
    assert captured.value.retry_after_seconds == 7


def test_503_is_transient() -> None:
    with _client(httpx.Response(503)) as client, pytest.raises(ProviderTransientError):
        client.request("GET", "/resource")


def test_422_is_permanent() -> None:
    with _client(httpx.Response(422)) as client, pytest.raises(ProviderPermanentError):
        client.request("POST", "/resource")


def test_read_timeout_is_marked_ambiguous() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with ProviderHttpClient(
        base_url="https://provider.example",
        transport=httpx.MockTransport(handler),
    ) as client, pytest.raises(ProviderTransportError) as captured:
        client.request("POST", "/resource")
    assert captured.value.operation_may_have_completed is True
