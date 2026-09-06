"""Deterministic pre-enrichment priority tests over search-only evidence."""

from __future__ import annotations

import pytest

from app.sourcing.prioritization import assess_enrichment_priority
from app.sourcing.schemas import EnrichmentPriority, PhoneAvailability


@pytest.mark.parametrize(
    ("title", "phone", "expected"),
    [
        ("Backend Engineer", PhoneAvailability.AVAILABLE, EnrichmentPriority.RECOMMENDED),
        ("Backend Engineer", PhoneAvailability.MAYBE, EnrichmentPriority.RECOMMENDED),
        ("Backend Engineer", PhoneAvailability.UNAVAILABLE, EnrichmentPriority.POSSIBLE),
        ("Backend Engineer", PhoneAvailability.UNKNOWN, EnrichmentPriority.POSSIBLE),
        ("API Engineer", PhoneAvailability.AVAILABLE, EnrichmentPriority.POSSIBLE),
        ("Account Executive", PhoneAvailability.AVAILABLE, EnrichmentPriority.LOW_PRIORITY),
        (None, PhoneAvailability.AVAILABLE, EnrichmentPriority.LOW_PRIORITY),
        (None, PhoneAvailability.UNKNOWN, EnrichmentPriority.LOW_PRIORITY),
    ],
)
def test_priority_keeps_contactability_subordinate_to_exact_role_evidence(
    title: str | None,
    phone: PhoneAvailability,
    expected: EnrichmentPriority,
) -> None:
    assessment = assess_enrichment_priority(
        current_title=title,
        target_titles=["Backend Engineer", "API Engineer"],
        phone_availability=phone,
        email_available=False,
        locations_requested=True,
    )

    assert assessment.priority is expected
    assert assessment.algorithm_version == "search_evidence_priority_v1"
    assert any(reason.code.startswith("phone_") for reason in assessment.reasons)


def test_priority_normalizes_only_unicode_whitespace_and_case() -> None:
    exact = assess_enrichment_priority(
        current_title="  BACKEND   ENGINEER ",
        target_titles=["Backend Engineer"],
        phone_availability=PhoneAvailability.AVAILABLE,
        email_available=True,
        locations_requested=False,
    )
    inferred = assess_enrichment_priority(
        current_title="Senior Backend Engineer",
        target_titles=["Backend Engineer"],
        phone_availability=PhoneAvailability.AVAILABLE,
        email_available=True,
        locations_requested=False,
    )

    assert exact.priority is EnrichmentPriority.RECOMMENDED
    assert inferred.priority is EnrichmentPriority.LOW_PRIORITY


def test_empty_search_page_requires_no_priority_side_effects() -> None:
    assessments = [
        assess_enrichment_priority(
            current_title=title,
            target_titles=["Backend Engineer"],
            phone_availability=PhoneAvailability.UNKNOWN,
            email_available=False,
            locations_requested=False,
        )
        for title in []
    ]

    assert assessments == []
