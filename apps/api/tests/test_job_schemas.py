"""Unit tests for Module 1 typed Job and screening-question contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.jobs.schemas import (
    JobDefinitionCreate,
    JobRequirements,
    ScreeningAnswerType,
    ScreeningQuestionCreate,
)


def test_requirements_trim_and_case_insensitive_deduplicate() -> None:
    requirements = JobRequirements(
        alternate_titles=[" Backend Engineer ", "backend engineer", "Python Engineer"],
        required_skills=[" Python ", "python", "FastAPI"],
        locations=[" Bengaluru ", "bengaluru"],
    )

    assert requirements.alternate_titles == ["Backend Engineer", "Python Engineer"]
    assert requirements.required_skills == ["Python", "FastAPI"]
    assert requirements.locations == ["Bengaluru"]


def test_requirements_reject_required_preferred_overlap() -> None:
    with pytest.raises(ValidationError):
        JobRequirements(required_skills=["Python"], preferred_skills=["python"])


def test_whitespace_only_required_text_is_rejected_after_normalization() -> None:
    with pytest.raises(ValidationError):
        JobDefinitionCreate(title="   ", description="x" * 30)

    with pytest.raises(ValidationError):
        JobDefinitionCreate(title="Engineer", description=" " * 30)


def test_choice_question_requires_at_least_two_unique_options() -> None:
    with pytest.raises(ValidationError):
        ScreeningQuestionCreate(
            key="availability",
            prompt="When can you start?",
            answer_type=ScreeningAnswerType.CHOICE,
            options=["Now", " now "],
        )


def test_non_choice_question_rejects_options() -> None:
    with pytest.raises(ValidationError):
        ScreeningQuestionCreate(
            key="interest",
            prompt="Are you interested?",
            answer_type=ScreeningAnswerType.YES_NO,
            options=["Yes", "No"],
        )


def test_question_key_is_normalized_before_pattern_validation() -> None:
    question = ScreeningQuestionCreate(
        key=" Python_Experience ",
        prompt="How many years of Python experience do you have?",
        answer_type=ScreeningAnswerType.NUMBER,
    )
    assert question.key == "python_experience"
