"""Unit tests for evidence-bounded Module 4 scoring and semantic merge behavior."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.matching.schemas import (
    MatchCriterionStatus,
    MatchInputSnapshot,
    MatchProfessionalEvidence,
    MatchProfessionalExperience,
    SemanticCriterionVerdict,
    SemanticMatchOutput,
)
from app.matching.scoring import (
    build_deterministic_criteria,
    build_semantic_evidence,
    calculate_score,
    hash_match_input,
    merge_semantic_output,
)


def snapshot(**updates):
    base = MatchInputSnapshot(
        job_id=uuid4(),
        definition_version=2,
        job_title="Senior Backend Engineer",
        alternate_titles=["Backend Engineer"],
        locations=["Bangalore"],
        seniority=["senior"],
        required_skills=["Python", "FastAPI"],
        preferred_skills=["PostgreSQL"],
        min_years_experience=5,
        employment_type="full_time",
        work_arrangement="hybrid",
        candidate_id=uuid4(),
        candidate_current_title="Backend Engineer",
        candidate_location="Bangalore",
    )
    return base.model_copy(update=updates)


def by_key(criteria):
    return {item.key: item for item in criteria}


def test_exact_role_and_location_are_supported_but_missing_skills_stay_unknown() -> None:
    criteria = by_key(build_deterministic_criteria(snapshot()))

    assert criteria["role_alignment"].status is MatchCriterionStatus.SUPPORTED
    assert criteria["location"].status is MatchCriterionStatus.SUPPORTED
    assert criteria["required_skill_1"].status is MatchCriterionStatus.UNKNOWN
    assert criteria["required_skill_2"].status is MatchCriterionStatus.UNKNOWN
    assert criteria["minimum_experience"].status is MatchCriterionStatus.UNKNOWN
    assert criteria["employment_type"].status is MatchCriterionStatus.UNKNOWN
    assert criteria["work_arrangement"].status is MatchCriterionStatus.UNKNOWN


def test_known_location_mismatch_is_contradicted_without_fuzzy_geography() -> None:
    criteria = by_key(
        build_deterministic_criteria(snapshot(candidate_location="Mumbai"))
    )

    assert criteria["location"].status is MatchCriterionStatus.CONTRADICTED


def test_semantic_title_output_can_classify_role_and_seniority_but_not_skills() -> None:
    current = snapshot(
        candidate_current_title="Platform Engineer",
        professional_evidence=MatchProfessionalEvidence(
            current_title="Platform Engineer",
            employment_history=[
                MatchProfessionalExperience(title="Backend Developer", is_current=False)
            ],
        ),
    )
    criteria = build_deterministic_criteria(current)
    evidence = build_semantic_evidence(current)
    output = SemanticMatchOutput(
        role_alignment=SemanticCriterionVerdict(
            status="supported",
            evidence_ids=[evidence[0].id],
            reason="The explicit role title is aligned with backend platform engineering.",
        ),
        seniority_alignment=SemanticCriterionVerdict(
            status="unknown",
            evidence_ids=[],
            reason="The supplied titles do not establish seniority reliably.",
        ),
    )

    merged = by_key(
        merge_semantic_output(
            criteria,
            output,
            valid_evidence_ids={item.id for item in evidence},
        )
    )

    assert merged["role_alignment"].status is MatchCriterionStatus.SUPPORTED
    assert merged["seniority"].status is MatchCriterionStatus.UNKNOWN
    assert merged["required_skill_1"].status is MatchCriterionStatus.UNKNOWN


def test_semantic_output_cannot_cite_invented_evidence() -> None:
    current = snapshot(candidate_current_title="Platform Engineer")
    criteria = build_deterministic_criteria(current)
    output = SemanticMatchOutput(
        role_alignment={
            "status": "supported",
            "evidence_ids": ["E999"],
            "reason": "Invented citation.",
        },
        seniority_alignment={
            "status": "unknown",
            "evidence_ids": [],
            "reason": "Unknown.",
        },
    )

    with pytest.raises(ValueError):
        merge_semantic_output(criteria, output, valid_evidence_ids={"E1"})


def test_score_and_coverage_are_distinct_and_score_never_exceeds_coverage() -> None:
    criteria = build_deterministic_criteria(snapshot(candidate_location="Mumbai"))
    result = calculate_score(criteria)

    assert result.match_score <= result.evidence_coverage
    assert result.evidence_coverage > result.match_score


def test_contact_only_revision_is_not_part_of_match_input_hash() -> None:
    current = snapshot()

    assert hash_match_input(current) == hash_match_input(current.model_copy())


def test_historical_exact_title_does_not_override_canonical_current_role() -> None:
    current = snapshot(
        candidate_current_title="Sales Manager",
        professional_evidence=MatchProfessionalEvidence(
            current_title="Sales Manager",
            employment_history=[
                MatchProfessionalExperience(
                    title="Senior Backend Engineer",
                    started_at="2022-01-01",
                    is_current=False,
                )
            ],
        ),
    )

    criteria = by_key(build_deterministic_criteria(current))

    assert criteria["role_alignment"].status is MatchCriterionStatus.UNKNOWN


def test_provider_current_title_can_supply_role_when_candidate_core_title_is_missing() -> None:
    current = snapshot(
        candidate_current_title=None,
        professional_evidence=MatchProfessionalEvidence(
            current_title="Backend Engineer",
            employment_history=[],
        ),
    )

    criteria = by_key(build_deterministic_criteria(current))

    assert criteria["role_alignment"].status is MatchCriterionStatus.SUPPORTED


def test_candidate_core_location_wins_over_conflicting_provider_location() -> None:
    current = snapshot(
        candidate_location="Mumbai",
        professional_evidence=MatchProfessionalEvidence(
            current_title="Backend Engineer",
            location="Bangalore",
            employment_history=[],
        ),
    )

    criteria = by_key(build_deterministic_criteria(current))

    assert criteria["location"].status is MatchCriterionStatus.CONTRADICTED


def test_semantic_evidence_preserves_employment_temporal_context() -> None:
    current = snapshot(
        professional_evidence=MatchProfessionalEvidence(
            current_title="Platform Engineer",
            employment_history=[
                MatchProfessionalExperience(
                    title="Backend Developer",
                    started_at="2021-04-01",
                    is_current=False,
                )
            ],
        )
    )

    evidence = build_semantic_evidence(current)
    history = next(item for item in evidence if item.source == "employment_history")

    assert history.started_at is not None
    assert history.started_at.isoformat() == "2021-04-01"
    assert history.is_current is False
