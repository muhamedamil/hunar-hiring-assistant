"""Deterministic Module 3 mapping tests against immutable approved Job definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.jobs.schemas import ApprovedJobDefinition
from app.sourcing.mapping import MAPPING_VERSION, build_search_mapping


def approved_definition() -> ApprovedJobDefinition:
    """Return a representative approved Job containing mapped and unmapped requirements."""

    return ApprovedJobDefinition(
        id=uuid4(),
        job_id=uuid4(),
        version=2,
        title="Senior Backend Engineer",
        company_name="Hunar.ai",
        description="Build reliable backend services for a production AI hiring platform.",
        requirements={
            "alternate_titles": ["Backend Engineer", "senior backend engineer"],
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["AWS"],
            "locations": ["Bangalore"],
            "min_years_experience": 5,
            "seniority": ["senior", "lead", "executive"],
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
        },
        screening_questions=[],
        created_at=datetime.now(UTC),
    )


def test_mapping_uses_only_exact_apollo_semantics() -> None:
    definition = approved_definition()

    criteria, query = build_search_mapping(definition, result_limit=25)

    assert MAPPING_VERSION == "apollo_people_search_v1"
    assert criteria.titles == ["Senior Backend Engineer", "Backend Engineer"]
    assert query.person_titles == criteria.titles
    assert query.person_locations == ["Bangalore"]
    assert query.person_seniorities == ["senior"]
    assert query.include_similar_titles is False
    assert query.page == 1
    assert query.per_page == 25

    unmapped = {item.field: item.values for item in criteria.unmapped_requirements}
    assert unmapped == {
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["AWS"],
        "seniority": ["lead", "executive"],
        "min_years_experience": ["5"],
        "employment_type": ["full_time"],
        "work_arrangement": ["hybrid"],
    }


def test_mapping_does_not_convert_skills_to_keyword_search() -> None:
    _, query = build_search_mapping(approved_definition(), result_limit=10)

    payload = query.model_dump(mode="json")
    assert "q_keywords" not in payload
    assert payload["per_page"] == 10
