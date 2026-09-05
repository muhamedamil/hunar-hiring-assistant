from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.retry import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
)


@dataclass(frozen=True)
class HttpTimeouts:
    connect: float = 5.0
    read: float = 20.0
    write: float = 10.0
    pool: float = 5.0

    def to_httpx(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect,
            read=self.read,
            write=self.write,
            pool=self.pool,
        )



def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


class ProviderHttpClient:
    """Shared provider HTTP conventions.

    This class intentionally performs **zero automatic retries**. It classifies transport
    and HTTP failures so the provider integration that understands operation semantics can
    decide whether repeating the request is safe.
    """

    def __init__(
        self,
        *,
        base_url: str,
        default_headers: dict[str, str] | None = None,
        timeouts: HttpTimeouts | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers=default_headers,
            timeout=(timeouts or HttpTimeouts()).to_httpx(),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ProviderHttpClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except (httpx.ConnectTimeout, httpx.ConnectError) as exc:
            raise ProviderTransportError(
                code="PROVIDER_CONNECT_FAILURE",
                message="Could not connect to provider.",
                operation_may_have_completed=False,
            ) from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError) as exc:
            raise ProviderTransportError(
                code="PROVIDER_TRANSPORT_UNCERTAIN",
                message="Provider request outcome is uncertain.",
                operation_may_have_completed=True,
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderTransportError(
                code="PROVIDER_TRANSPORT_FAILURE",
                message="Provider transport failed.",
                operation_may_have_completed=True,
            ) from exc

        self._raise_for_provider_status(response)
        return response

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderInvalidResponseError(
                code="PROVIDER_INVALID_JSON",
                message="Provider returned an invalid JSON response.",
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _raise_for_provider_status(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return

        common = {"status_code": status}

        if status in {401, 403}:
            raise ProviderAuthenticationError(
                code="PROVIDER_AUTHENTICATION_ERROR",
                message="Provider authentication or authorization failed.",
                **common,
            )

        if status == 429:
            raise ProviderRateLimitError(
                code="PROVIDER_RATE_LIMITED",
                message="Provider rate limit reached.",
                retry_after_seconds=parse_retry_after(response.headers.get("Retry-After")),
                **common,
            )

        if status in {500, 502, 503, 504}:
            raise ProviderTransientError(
                code="PROVIDER_TRANSIENT_ERROR",
                message="Provider is temporarily unavailable.",
                **common,
            )

        raise ProviderPermanentError(
            code="PROVIDER_REQUEST_REJECTED",
            message="Provider rejected the request.",
            **common,
        )
