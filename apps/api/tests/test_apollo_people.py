"""Apollo adapter tests for bounded search, enrichment ambiguity, webhook parsing, and polling."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.retry import ProviderInvalidResponseError
from app.integrations.apollo.errors import ApolloAmbiguousEnrichmentError
from app.integrations.apollo.people import ApolloPeopleProvider
from app.sourcing.schemas import ProviderPollStatus, ProviderSearchQuery


def provider(handler):  # type: ignore[no-untyped-def]
    """Build an Apollo adapter over an in-memory HTTP transport."""

    return ApolloPeopleProvider(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )


def test_search_maps_query_and_returns_normalized_contact_free_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/mixed_people/api_search")
        assert request.url.params.get_list("person_titles[]") == ["Backend Engineer"]
        assert request.url.params["include_similar_titles"] == "false"
        assert request.url.params["per_page"] == "10"
        return httpx.Response(
            200,
            json={
                "people": [
                    {
                        "person_id": "person-1",
                        "first_name": "Sarah",
                        "last_name_obfuscated": "Ah***d",
                        "title": "Backend Engineer",
                        "organization": {"name": "Acme"},
                        "has_email": True,
                        "has_direct_phone": "Yes",
                    }
                ],
                "pagination": {"total_entries": 123},
            },
        )

    adapter = provider(handler)
    page = adapter.search_people(
        ProviderSearchQuery(person_titles=["Backend Engineer"], per_page=10)
    )

    assert page.total_matches == 123
    assert len(page.hits) == 1
    hit = page.hits[0]
    assert hit.external_person_id == "person-1"
    assert hit.last_name_obfuscated == "Ah***d"
    assert hit.email_available is True
    assert hit.phone_availability.value == "available"


def test_search_maps_apollo_maybe_phone_signal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "people": [
                    {
                        "id": "person-1",
                        "has_direct_phone": "Maybe: request direct dial via people/bulk_match",
                    }
                ]
            },
        )

    adapter = provider(handler)
    page = adapter.search_people(
        ProviderSearchQuery(person_titles=["Backend Engineer"], per_page=10)
    )

    assert page.hits[0].phone_availability.value == "maybe"


def test_search_rejects_provider_page_larger_than_requested_bound() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        people = [{"person_id": f"person-{index}"} for index in range(11)]
        return httpx.Response(200, json={"people": people})

    adapter = provider(handler)
    with pytest.raises(ProviderInvalidResponseError) as exc_info:
        adapter.search_people(
            ProviderSearchQuery(person_titles=["Backend Engineer"], per_page=10)
        )

    assert exc_info.value.code == "APOLLO_SEARCH_RESPONSE_INVALID"


def test_enrichment_without_request_id_is_ambiguous_when_phone_was_requested() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/people/match")
        assert request.url.params["reveal_phone_number"] == "true"
        return httpx.Response(
            200,
            json={
                "person": {
                    "id": "person-1",
                    "name": "Sarah Ahmed",
                    "title": "Backend Engineer",
                    "email": "sarah@example.com",
                }
            },
        )

    adapter = provider(handler)
    with pytest.raises(ApolloAmbiguousEnrichmentError) as exc_info:
        adapter.enrich_person(
            external_person_id="person-1",
            webhook_url="https://example.test/webhook",
        )

    assert exc_info.value.code == "APOLLO_ENRICHMENT_REQUEST_ID_MISSING"


def test_enrichment_rejects_mismatched_provider_person_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "request_id": 123,
                "person": {"id": "different-person", "name": "Sarah Ahmed"},
            },
        )

    adapter = provider(handler)
    with pytest.raises(ProviderInvalidResponseError) as exc_info:
        adapter.enrich_person(
            external_person_id="person-1",
            webhook_url="https://example.test/webhook",
        )

    assert exc_info.value.code == "APOLLO_ENRICHMENT_RESPONSE_INVALID"


def test_native_phone_result_rejects_multiple_people_for_single_enrichment() -> None:
    payload = {
        "people": [
            {"id": "person-1", "phone_numbers": []},
            {"id": "person-2", "phone_numbers": []},
        ]
    }

    with pytest.raises(ProviderInvalidResponseError) as exc_info:
        ApolloPeopleProvider.parse_phone_result(payload)

    assert exc_info.value.code == "APOLLO_PHONE_RESULT_INVALID"


def test_enrichment_accepts_negative_signed_64_bit_request_id() -> None:
    request_id = -1039995589705121900

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "request_id": str(request_id),
                "person": {"id": "person-1", "name": "Sarah Ahmed"},
            },
        )

    adapter = provider(handler)
    response = adapter.enrich_person(
        external_person_id="person-1",
        webhook_url="https://example.test/webhook",
    )

    assert response.request_id == request_id
    assert response.person is not None


def test_poll_preserves_result_pending_semantics_instead_of_generic_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/webhook_result/123")
        return httpx.Response(
            404,
            json={"error_code": "result_pending", "retry_after_seconds": 17},
        )

    adapter = provider(handler)
    result = adapter.poll_enrichment(123)

    assert result.status is ProviderPollStatus.PENDING
    assert result.retry_after_seconds == 17


def test_native_phone_webhook_is_normalized_without_raw_payload_retention() -> None:
    payload = json.loads(
        """
        {
          "status": "success",
          "credits_consumed": 8,
          "people": [{
            "id": "person-1",
            "phone_numbers": [{
              "position": 0,
              "raw_number": "+1 202-555-0116",
              "sanitized_number": "+12025550116",
              "status_cd": "valid_number",
              "type_cd": "mobile"
            }]
          }]
        }
        """
    )

    adapter = provider(lambda request: httpx.Response(200, json={}))
    result = adapter.parse_phone_result(payload)

    assert result.external_person_id == "person-1"
    assert result.credits_consumed == 8
    assert result.phones[0].sanitized_number == "+12025550116"
