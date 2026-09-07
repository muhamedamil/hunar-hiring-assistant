"""Zero-retry Hunar External API v1 adapter for preflight and call creation only."""

from __future__ import annotations

from contextlib import suppress
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.http_client import HttpTimeouts, ProviderHttpClient
from app.core.retry import ProviderInvalidResponseError
from app.integrations.hunar.errors import HunarAmbiguousResponseError
from app.integrations.hunar.schemas import (
    HunarAgentDetail,
    HunarCallCreateCommand,
    HunarCallCreateResponse,
    HunarCallStatus,
)


class HunarVoiceProvider:
    """Own one HTTP client; no agent provisioning, polling or callback receiver methods."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        read_timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = ProviderHttpClient(
            base_url=base_url.rstrip("/") + "/",
            default_headers={"X-API-Key": api_key},
            timeouts=HttpTimeouts(read=read_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._http.close()

    def get_agent(self, agent_id: UUID) -> HunarAgentDetail:
        """Fetch read-only preflight evidence; missing required evidence is invalid."""
        raw = self._http.request_json("GET", f"agents/{agent_id}/")
        try:
            return HunarAgentDetail.model_validate(raw)
        except ValidationError:
            raise ProviderInvalidResponseError(
                code="HUNAR_AGENT_RESPONSE_INVALID", message="Agent response is invalid."
            ) from None

    def create_call(self, command: HunarCallCreateCommand) -> HunarCallCreateResponse:
        """Submit once; malformed or inconsistent success always preserves uncertainty."""
        raw = self._http.request_json(
            "POST", "calls/", json=command.model_dump(mode="json", exclude_none=True)
        )
        try:
            result = HunarCallCreateResponse.model_validate(raw)
            for field in ("request_id", "callee_name", "mobile_number", "timezone"):
                if getattr(result, field) != getattr(command, field):
                    raise ValueError("Response echo mismatch")
            return result
        except (ValidationError, ValueError):
            call_id, initial_status = salvage_identity(raw)
            raise HunarAmbiguousResponseError(call_id, initial_status) from None


def salvage_identity(raw: object) -> tuple[UUID | None, HunarCallStatus | None]:
    """Independently salvage a UUID and documented status without trusting other response fields."""
    call_id = None
    status = None
    if isinstance(raw, dict):
        try:
            if isinstance(raw.get("id"), str):
                call_id = UUID(raw["id"])
        except ValueError:
            pass
        with suppress(ValueError, TypeError):
            status = HunarCallStatus(str(raw.get("status")))
    return call_id, status
