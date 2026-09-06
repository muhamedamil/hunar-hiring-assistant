"""Deterministic approved-Job to provider-search mapping for Module 3."""

from __future__ import annotations

from app.jobs.schemas import ApprovedJobDefinition
from app.sourcing.schemas import (
    ProviderSearchQuery,
    SourcingSearchCriteria,
    UnmappedRequirement,
)

MAPPING_VERSION = "apollo_people_search_v1"
_EXACT_SENIORITIES = {"intern", "entry", "senior", "manager", "director"}


def _dedupe(values: list[str]) -> list[str]:
    """Return trimmed values with case-insensitive stable-order deduplication."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def build_search_mapping(
    definition: ApprovedJobDefinition,
    *,
    result_limit: int,
) -> tuple[SourcingSearchCriteria, ProviderSearchQuery]:
    """Map only semantically exact Job fields into Apollo people-search filters."""

    requirements = definition.requirements
    titles = _dedupe([definition.title, *requirements.alternate_titles])
    locations = _dedupe(requirements.locations)
    canonical_seniorities = [value.value for value in requirements.seniority]
    mapped_seniorities = [
        value for value in canonical_seniorities if value in _EXACT_SENIORITIES
    ]
    unmapped: list[UnmappedRequirement] = []

    if requirements.required_skills:
        unmapped.append(
            UnmappedRequirement(field="required_skills", values=requirements.required_skills)
        )
    if requirements.preferred_skills:
        unmapped.append(
            UnmappedRequirement(field="preferred_skills", values=requirements.preferred_skills)
        )
    unsupported_seniority = [
        value for value in canonical_seniorities if value not in _EXACT_SENIORITIES
    ]
    if unsupported_seniority:
        unmapped.append(
            UnmappedRequirement(field="seniority", values=unsupported_seniority)
        )
    if requirements.min_years_experience is not None:
        unmapped.append(
            UnmappedRequirement(
                field="min_years_experience",
                values=[str(requirements.min_years_experience)],
            )
        )
    if requirements.employment_type is not None:
        unmapped.append(
            UnmappedRequirement(
                field="employment_type",
                values=[requirements.employment_type.value],
            )
        )
    if requirements.work_arrangement is not None:
        unmapped.append(
            UnmappedRequirement(
                field="work_arrangement",
                values=[requirements.work_arrangement.value],
            )
        )

    criteria = SourcingSearchCriteria(
        titles=titles,
        locations=locations,
        seniorities=mapped_seniorities,
        unmapped_requirements=unmapped,
        result_limit=result_limit,
    )
    query = ProviderSearchQuery(
        person_titles=titles,
        person_locations=locations,
        person_seniorities=mapped_seniorities,
        include_similar_titles=False,
        page=1,
        per_page=result_limit,
    )
    return criteria, query
