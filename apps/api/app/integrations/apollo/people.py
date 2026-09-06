"""Apollo People Search, enrichment, webhook, and poll adapter for Module 3."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.http_client import HttpTimeouts, ProviderHttpClient
from app.core.retry import ProviderInvalidResponseError
from app.integrations.apollo.errors import ApolloAmbiguousEnrichmentError
from app.integrations.apollo.schemas import (
    optional_text,
    parse_date,
    parse_datetime,
    require_list,
    require_object,
)
from app.sourcing.schemas import (
    CandidateProfessionalEvidence,
    PhoneAvailability,
    ProfessionalExperienceEvidence,
    ProviderEnrichedPerson,
    ProviderEnrichmentResponse,
    ProviderPhoneNumber,
    ProviderPhoneResult,
    ProviderPollResult,
    ProviderPollStatus,
    ProviderSearchHit,
    ProviderSearchPage,
    ProviderSearchQuery,
)


class ApolloPeopleProvider:
    """Translate Apollo HTTP contracts into strict provider-neutral sourcing contracts."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.apollo.io/api/v1",
        search_read_timeout_seconds: float = 30.0,
        enrichment_read_timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": api_key,
        }
        self._search_client = ProviderHttpClient(
            base_url=base_url,
            default_headers=headers,
            timeouts=HttpTimeouts(read=search_read_timeout_seconds),
            transport=transport,
        )
        self._enrichment_client = ProviderHttpClient(
            base_url=base_url,
            default_headers=headers,
            timeouts=HttpTimeouts(read=enrichment_read_timeout_seconds),
            transport=transport,
        )

    def close(self) -> None:
        """Close underlying HTTP clients."""

        self._search_client.close()
        self._enrichment_client.close()

    def search_people(self, query: ProviderSearchQuery) -> ProviderSearchPage:
        """Search Apollo once and reject any page exceeding the requested bound."""

        params: list[tuple[str, str]] = []
        params.extend(("person_titles[]", value) for value in query.person_titles)
        params.extend(("person_locations[]", value) for value in query.person_locations)
        params.extend(("person_seniorities[]", value) for value in query.person_seniorities)
        params.extend(
            [
                ("include_similar_titles", "true" if query.include_similar_titles else "false"),
                ("page", str(query.page)),
                ("per_page", str(query.per_page)),
            ]
        )
        payload = self._search_client.request_json(
            "POST",
            "/mixed_people/api_search",
            params=params,
        )
        return self._parse_search_page(payload, requested_limit=query.per_page)

    def enrich_person(
        self,
        *,
        external_person_id: str,
        webhook_url: str,
    ) -> ProviderEnrichmentResponse:
        """Start native Apollo person enrichment with asynchronous phone reveal."""

        payload = self._enrichment_client.request_json(
            "POST",
            "/people/match",
            params={
                "id": external_person_id,
                "reveal_personal_emails": "false",
                "reveal_phone_number": "true",
                "webhook_url": webhook_url,
            },
        )
        response = self._parse_enrichment_response(payload, expected_person_id=external_person_id)
        if response.person is not None and response.request_id is None:
            raise ApolloAmbiguousEnrichmentError(
                code="APOLLO_ENRICHMENT_REQUEST_ID_MISSING",
                message=(
                    "Apollo matched the person but omitted the phone-enrichment request ID; "
                    "the credit-consuming outcome cannot be recovered safely."
                ),
            )
        return response

    def poll_enrichment(self, request_id: int) -> ProviderPollResult:
        """Poll Apollo's zero-credit webhook-result endpoint using semantic HTTP statuses."""

        status, payload = self._enrichment_client.request_json_with_status(
            "GET",
            f"/webhook_result/{request_id}",
            allowed_statuses={400, 404, 410},
        )
        if status == 200:
            phone_result = self.parse_phone_result(payload)
            return ProviderPollResult(
                status=ProviderPollStatus.COMPLETED,
                phone_result=ProviderPhoneResult(
                    request_id=request_id,
                    external_person_id=phone_result.external_person_id,
                    phones=phone_result.phones,
                    credits_consumed=phone_result.credits_consumed,
                ),
            )

        body = require_object(payload, context="Apollo poll error response")
        error_code = optional_text(body.get("error_code")) or "APOLLO_POLL_REJECTED"
        if status == 404 and error_code == "result_pending":
            retry_after = body.get("retry_after_seconds")
            retry_seconds = int(retry_after) if isinstance(retry_after, (int, float)) else 30
            return ProviderPollResult(
                status=ProviderPollStatus.PENDING,
                retry_after_seconds=max(0, retry_seconds),
            )
        return ProviderPollResult(
            status=ProviderPollStatus.TERMINAL_FAILURE,
            failure_code=error_code,
        )

    @staticmethod
    def parse_phone_result(payload: object) -> ProviderPhoneResult:
        """Normalize Apollo native phone webhook/poll payload without retaining raw JSON."""

        try:
            body = require_object(payload, context="Apollo phone result")
            people = require_list(body.get("people", []), context="Apollo phone result people")
            if len(people) != 1:
                raise ValueError(
                    "Apollo single-person phone result must contain exactly one person"
                )
            person = require_object(people[0], context="Apollo phone result person")
            external_person_id = optional_text(person.get("id"))
            if external_person_id is None:
                raise ValueError("Apollo phone result is missing person ID")
            phone_values = require_list(
                person.get("phone_numbers", []),
                context="Apollo phone result phone_numbers",
            )
            phones: list[ProviderPhoneNumber] = []
            for value in phone_values:
                item = require_object(value, context="Apollo phone number")
                position = item.get("position")
                phones.append(
                    ProviderPhoneNumber(
                        raw_number=optional_text(item.get("raw_number")),
                        sanitized_number=optional_text(item.get("sanitized_number")),
                        type_code=optional_text(item.get("type_cd")),
                        status_code=optional_text(item.get("status_cd")),
                        position=position if isinstance(position, int) and position >= 0 else 0,
                    )
                )
            credits = body.get("credits_consumed")
            request_id = body.get("request_id")
            return ProviderPhoneResult(
                request_id=ApolloPeopleProvider._parse_request_id(request_id, required=False),
                external_person_id=external_person_id,
                phones=phones,
                credits_consumed=credits if isinstance(credits, int) and credits >= 0 else None,
            )
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                code="APOLLO_PHONE_RESULT_INVALID",
                message="Apollo returned an invalid phone-enrichment result.",
            ) from exc

    def _parse_search_page(self, payload: object, *, requested_limit: int) -> ProviderSearchPage:
        try:
            body = require_object(payload, context="Apollo people search response")
            people = require_list(body.get("people", []), context="Apollo people search people")
            if len(people) > requested_limit:
                raise ValueError("Apollo returned more people than the requested per_page bound")
            hits = [self._parse_search_hit(value) for value in people]
            pagination = body.get("pagination")
            total_matches: int | None = None
            if isinstance(pagination, dict):
                total = pagination.get("total_entries")
                if isinstance(total, int) and total >= 0:
                    total_matches = total
            if total_matches is None:
                total = body.get("total_entries")
                if isinstance(total, int) and total >= 0:
                    total_matches = total
            return ProviderSearchPage(hits=hits, total_matches=total_matches)
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                code="APOLLO_SEARCH_RESPONSE_INVALID",
                message="Apollo returned an invalid people-search response.",
            ) from exc

    @staticmethod
    def _parse_search_hit(value: object) -> ProviderSearchHit:
        person = require_object(value, context="Apollo people search person")
        external_person_id = optional_text(person.get("person_id")) or optional_text(
            person.get("id")
        )
        if external_person_id is None:
            raise ValueError("Apollo people search result is missing person ID")
        organization = person.get("organization")
        organization_name = None
        if isinstance(organization, dict):
            organization_name = optional_text(organization.get("name"))
        organization_name = organization_name or optional_text(person.get("organization_name"))
        has_phone = person.get("has_direct_phone")
        phone_signal = has_phone.strip().casefold() if isinstance(has_phone, str) else None
        if has_phone is True or phone_signal == "yes":
            phone_availability = PhoneAvailability.AVAILABLE
        elif phone_signal is not None and phone_signal.startswith("maybe"):
            phone_availability = PhoneAvailability.MAYBE
        elif has_phone is False or phone_signal in {"no", "false"}:
            phone_availability = PhoneAvailability.UNAVAILABLE
        else:
            phone_availability = PhoneAvailability.UNKNOWN
        return ProviderSearchHit(
            external_person_id=external_person_id,
            first_name=optional_text(person.get("first_name")),
            last_name_obfuscated=optional_text(person.get("last_name_obfuscated")),
            title=optional_text(person.get("title")),
            organization_name=organization_name,
            email_available=bool(person.get("has_email", False)),
            phone_availability=phone_availability,
            last_refreshed_at=parse_datetime(person.get("last_refreshed_at")),
        )

    def _parse_enrichment_response(
        self,
        payload: object,
        *,
        expected_person_id: str,
    ) -> ProviderEnrichmentResponse:
        try:
            body = require_object(payload, context="Apollo people enrichment response")
            request_id = self._parse_request_id(body.get("request_id"), required=False)
            value = body.get("person")
            if value is None:
                return ProviderEnrichmentResponse(person=None, request_id=request_id)
            person = require_object(value, context="Apollo enriched person")
            returned_person_id = optional_text(person.get("id"))
            if returned_person_id is not None and returned_person_id != expected_person_id:
                raise ValueError("Apollo enriched person ID does not match the requested person ID")
            external_person_id = returned_person_id or expected_person_id
            full_name = optional_text(person.get("name"))
            if full_name is None:
                first = optional_text(person.get("first_name")) or ""
                last = optional_text(person.get("last_name")) or ""
                full_name = " ".join(part for part in (first, last) if part).strip()
            if not full_name:
                raise ValueError("Apollo enriched person is missing a canonical full name")
            organization = person.get("organization")
            company = None
            if isinstance(organization, dict):
                company = optional_text(organization.get("name"))
            location = self._location(person)
            enriched = ProviderEnrichedPerson.model_validate(
                {
                    "external_person_id": external_person_id,
                    "full_name": full_name,
                    "title": optional_text(person.get("title")),
                    "company": company,
                    "location": location,
                    "email": optional_text(person.get("email")),
                    "linkedin_url": optional_text(person.get("linkedin_url")),
                }
            )
            professional_evidence = self._professional_evidence(person, enriched)
            return ProviderEnrichmentResponse(
                person=enriched,
                request_id=request_id,
                professional_evidence=professional_evidence,
            )
        except (TypeError, ValueError) as exc:
            raise ProviderInvalidResponseError(
                code="APOLLO_ENRICHMENT_RESPONSE_INVALID",
                message="Apollo returned an invalid person-enrichment response.",
            ) from exc

    @staticmethod
    def _location(person: dict[str, Any]) -> str | None:
        parts = [
            optional_text(person.get("city")),
            optional_text(person.get("state")),
            optional_text(person.get("country")),
        ]
        values = [part for part in parts if part]
        return ", ".join(values) if values else None

    @staticmethod
    def _professional_evidence(
        person: dict[str, Any],
        enriched: ProviderEnrichedPerson,
    ) -> CandidateProfessionalEvidence:
        history_value = person.get("employment_history", [])
        history: list[ProfessionalExperienceEvidence] = []
        if isinstance(history_value, list):
            for value in history_value[:100]:
                if not isinstance(value, dict):
                    continue
                title = optional_text(value.get("title"))
                organization_name = optional_text(value.get("organization_name"))
                started_at = parse_date(value.get("start_date"))
                current = value.get("current")
                is_current = current if isinstance(current, bool) else None
                if not any((title, organization_name, started_at, is_current is not None)):
                    continue
                history.append(
                    ProfessionalExperienceEvidence(
                        title=title,
                        organization_name=organization_name,
                        started_at=started_at,
                        is_current=is_current,
                    )
                )
        return CandidateProfessionalEvidence(
            current_title=enriched.title,
            current_organization_name=enriched.company,
            location=enriched.location,
            profile_url=enriched.linkedin_url,
            employment_history=history,
        )

    @staticmethod
    def _parse_request_id(value: object, *, required: bool) -> int | None:
        if value is None and not required:
            return None
        if isinstance(value, bool):
            raise ValueError("Apollo request_id must be a signed 64-bit integer")
        if not isinstance(value, (int, str)):
            raise ValueError("Apollo request_id must be a signed 64-bit integer")
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError("Apollo request_id must be a signed 64-bit integer") from exc
        if parsed < -(2**63) or parsed > 2**63 - 1:
            raise ValueError("Apollo request_id exceeds signed 64-bit range")
        return parsed
