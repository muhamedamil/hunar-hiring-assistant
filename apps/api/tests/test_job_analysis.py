"""Tests for provider-neutral JD analysis orchestration and failure mapping."""

from __future__ import annotations

import pytest

from app.core.retry import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
)
from app.jobs.analysis import JobAnalysisService
from app.jobs.errors import (
    JobAnalysisConfigError,
    JobAnalysisInvalidResponseError,
    JobAnalysisRateLimitedError,
    JobAnalysisUnavailableError,
)
from app.jobs.schemas import JobAnalysisProviderOutput, ScreeningAnswerType


class StaticProvider:
    """Return a fixed provider output for normalization tests."""

    def __init__(self, output: JobAnalysisProviderOutput) -> None:
        self.output = output

    def analyze(self, *, title: str | None, description: str) -> JobAnalysisProviderOutput:
        assert description
        return self.output


class FailingProvider:
    """Raise one provider error to verify stable application-level mapping."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def analyze(self, *, title: str | None, description: str) -> JobAnalysisProviderOutput:
        del title, description
        raise self.error


def test_analysis_normalizes_skill_overlap_and_duplicate_question_keys() -> None:
    output = JobAnalysisProviderOutput(
        suggested_title="Senior Python Engineer",
        requirements={
            "alternate_titles": [],
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["python", "AWS"],
            "locations": [],
            "min_years_experience": None,
            "seniority": [],
            "employment_type": None,
            "work_arrangement": None,
        },
        suggested_screening_questions=[
            {
                "key": "interest",
                "prompt": "Are you interested in this role?",
                "answer_type": ScreeningAnswerType.YES_NO,
            },
            {
                "key": "interest",
                "prompt": "Would you like to continue?",
                "answer_type": ScreeningAnswerType.YES_NO,
            },
        ],
    )

    proposal = JobAnalysisService(StaticProvider(output)).analyze(
        title=None,
        description="A sufficiently long Job Description for analysis.",
    )

    assert proposal.requirements.required_skills == ["Python", "FastAPI"]
    assert proposal.requirements.preferred_skills == ["AWS"]
    assert [question.key for question in proposal.suggested_screening_questions] == ["interest"]


def test_analysis_rejects_title_only_proposal_as_not_usable() -> None:
    output = JobAnalysisProviderOutput(
        suggested_title="Senior Python Engineer",
        requirements={
            "alternate_titles": [],
            "required_skills": [],
            "preferred_skills": [],
            "locations": [],
            "min_years_experience": None,
            "seniority": [],
            "employment_type": None,
            "work_arrangement": None,
        },
        suggested_screening_questions=[],
    )

    with pytest.raises(JobAnalysisInvalidResponseError):
        JobAnalysisService(StaticProvider(output)).analyze(
            title="Senior Python Engineer",
            description="A sufficiently long Job Description for analysis.",
        )


@pytest.mark.parametrize(
    ("provider_error", "application_error"),
    [
        (
            ProviderAuthenticationError(code="AUTH", message="auth", status_code=401),
            JobAnalysisConfigError,
        ),
        (
            ProviderRateLimitError(
                code="RATE",
                message="rate",
                status_code=429,
                retry_after_seconds=10,
            ),
            JobAnalysisRateLimitedError,
        ),
        (
            ProviderTransientError(code="TEMP", message="temp", status_code=503),
            JobAnalysisUnavailableError,
        ),
        (
            ProviderTransportError(
                code="NET",
                message="network",
                operation_may_have_completed=False,
            ),
            JobAnalysisUnavailableError,
        ),
        (
            ProviderInvalidResponseError(code="BAD", message="bad"),
            JobAnalysisInvalidResponseError,
        ),
    ],
)
def test_provider_failures_map_to_stable_job_analysis_errors(
    provider_error: Exception,
    application_error: type[Exception],
) -> None:
    service = JobAnalysisService(FailingProvider(provider_error))
    with pytest.raises(application_error):
        service.analyze(title=None, description="A sufficiently long Job Description.")
