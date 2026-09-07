"""Ambiguous POST errors retain only safely observed provider identity."""

from uuid import UUID

from app.core.retry import ProviderInvalidResponseError
from app.integrations.hunar.schemas import HunarCallStatus


class HunarAmbiguousResponseError(ProviderInvalidResponseError):
    """Malformed acceptance may still identify a real call; never automatically replay."""

    def __init__(self, call_id: UUID | None, status: HunarCallStatus | None) -> None:
        super().__init__(code="HUNAR_AMBIGUOUS_RESPONSE", message="Call response is uncertain.")
        self.call_id = call_id
        self.initial_status = status
