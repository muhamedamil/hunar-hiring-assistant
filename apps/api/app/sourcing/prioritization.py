"""Pure pre-enrichment prioritization over frozen Job and provider search evidence."""

from __future__ import annotations

import unicodedata
from typing import Literal

from app.sourcing.schemas import (
    EnrichmentPriority,
    EnrichmentPriorityAssessment,
    EnrichmentPriorityReason,
    PhoneAvailability,
)

PRIORITY_ALGORITHM_VERSION = "search_evidence_priority_v1"


def assess_enrichment_priority(
    *,
    current_title: str | None,
    target_titles: list[str],
    phone_availability: PhoneAvailability,
    email_available: bool,
    locations_requested: bool,
) -> EnrichmentPriorityAssessment:
    """Recommend credit spend without inferring Candidate facts or hiring fitness."""

    reasons: list[EnrichmentPriorityReason] = []
    normalized_title = _normalize_title(current_title)
    normalized_targets = [_normalize_title(value) for value in target_titles]
    primary_match = bool(
        normalized_title
        and normalized_targets
        and normalized_title == normalized_targets[0]
    )
    alternate_match = bool(
        normalized_title and normalized_title in normalized_targets[1:]
    )

    if primary_match:
        reasons.append(_reason("primary_title_exact", "positive", "Exact target title"))
    elif alternate_match:
        reasons.append(
            _reason("alternate_title_exact", "positive", "Exact alternate target title")
        )
    elif normalized_title:
        reasons.append(
            _reason(
                "title_not_aligned",
                "negative",
                "Current title does not exactly align with target titles",
            )
        )
    else:
        reasons.append(
            _reason("title_unavailable", "unknown", "Current title is unavailable")
        )

    reasons.append(_phone_reason(phone_availability))
    reasons.append(
        _reason(
            "email_available" if email_available else "email_not_indicated",
            "positive" if email_available else "unknown",
            "Email may be available" if email_available else "Email availability is not indicated",
        )
    )
    if locations_requested:
        reasons.append(
            _reason(
                "location_evidence_unavailable",
                "unknown",
                "People Search does not return a usable location value",
            )
        )

    contactability_positive = phone_availability in {
        PhoneAvailability.AVAILABLE,
        PhoneAvailability.MAYBE,
    }
    if primary_match and contactability_positive:
        priority = EnrichmentPriority.RECOMMENDED
    elif primary_match or alternate_match:
        priority = EnrichmentPriority.POSSIBLE
    else:
        priority = EnrichmentPriority.LOW_PRIORITY

    return EnrichmentPriorityAssessment(
        priority=priority,
        reasons=reasons,
        algorithm_version=PRIORITY_ALGORITHM_VERSION,
    )


def _normalize_title(value: str | None) -> str:
    """Normalize only Unicode, surrounding whitespace, and case for exact comparison."""

    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _phone_reason(phone_availability: PhoneAvailability) -> EnrichmentPriorityReason:
    if phone_availability is PhoneAvailability.AVAILABLE:
        return _reason("phone_available", "positive", "Phone likely available")
    if phone_availability is PhoneAvailability.MAYBE:
        return _reason("phone_maybe", "positive", "Phone may be available")
    if phone_availability is PhoneAvailability.UNAVAILABLE:
        return _reason("phone_unavailable", "negative", "Phone is not indicated as available")
    return _reason("phone_unknown", "unknown", "Phone availability is unknown")


def _reason(
    code: str,
    outcome: Literal["positive", "negative", "unknown"],
    detail: str,
) -> EnrichmentPriorityReason:
    return EnrichmentPriorityReason.model_validate(
        {"code": code, "outcome": outcome, "detail": detail}
    )
