"""Provider-neutral protocols consumed by the Module 3 sourcing services."""

from __future__ import annotations

from typing import Protocol

from app.sourcing.schemas import (
    ProviderEnrichmentResponse,
    ProviderPhoneResult,
    ProviderPollResult,
    ProviderSearchPage,
    ProviderSearchQuery,
)


class PeopleSearchProvider(Protocol):
    """Contract for a provider that can perform bounded read-only people search."""

    def search_people(self, query: ProviderSearchQuery) -> ProviderSearchPage:
        """Return one validated bounded search page."""


class PeopleEnrichmentProvider(Protocol):
    """Contract for credit-aware person enrichment and zero-credit poll recovery."""

    def enrich_person(
        self,
        *,
        external_person_id: str,
        webhook_url: str,
    ) -> ProviderEnrichmentResponse:
        """Start one provider enrichment for an already selected search result."""

    def poll_enrichment(self, request_id: int) -> ProviderPollResult:
        """Poll an asynchronous enrichment result without starting a new enrichment."""

    def parse_phone_result(self, payload: object) -> ProviderPhoneResult:
        """Normalize one provider webhook body into a phone-result contract."""
