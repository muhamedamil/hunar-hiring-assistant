"""Non-mutating Job Description analysis orchestration and provider protocol."""

from __future__ import annotations

from typing import Protocol

from app.core.retry import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
)
from app.jobs.errors import (
    JobAnalysisConfigError,
    JobAnalysisInvalidResponseError,
    JobAnalysisRateLimitedError,
    JobAnalysisUnavailableError,
)
from app.jobs.schemas import (
    JobAnalysisProposal,
    JobAnalysisProviderOutput,
    JobRequirements,
    SuggestedScreeningQuestion,
)


class JobAnalysisProvider(Protocol):
    """Provider-neutral boundary for one structured Job Description analysis."""

    def analyze(self, *, title: str | None, description: str) -> JobAnalysisProviderOutput:
        """Return a non-authoritative structured proposal without mutating application state."""


class JobAnalysisService:
    """Map provider outcomes into stable application errors and normalize AI suggestions."""

    def __init__(self, provider: JobAnalysisProvider) -> None:
        self._provider = provider

    def analyze(self, *, title: str | None, description: str) -> JobAnalysisProposal:
        """Analyze a JD synchronously; callers may retry explicitly or continue manually."""

        try:
            provider_output = self._provider.analyze(title=title, description=description)
        except ProviderAuthenticationError as exc:
            raise JobAnalysisConfigError() from exc
        except ProviderRateLimitError as exc:
            raise JobAnalysisRateLimitedError() from exc
        except (ProviderTransientError, ProviderTransportError) as exc:
            raise JobAnalysisUnavailableError() from exc
        except ProviderInvalidResponseError as exc:
            raise JobAnalysisInvalidResponseError() from exc
        except ProviderPermanentError as exc:
            raise JobAnalysisConfigError() from exc
        proposal = self._normalize_proposal(provider_output)
        if not self._has_usable_suggestions(proposal):
            raise JobAnalysisInvalidResponseError()
        return proposal

    @staticmethod
    def _has_usable_suggestions(proposal: JobAnalysisProposal) -> bool:
        """Require qualification data; a title-only response does not help fill the editor."""

        requirements = proposal.requirements
        return bool(
            requirements.alternate_titles
            or requirements.required_skills
            or requirements.preferred_skills
            or requirements.locations
            or requirements.min_years_experience is not None
            or requirements.seniority
            or requirements.employment_type is not None
            or requirements.work_arrangement is not None
            or proposal.suggested_screening_questions
        )

    @staticmethod
    def _normalize_proposal(provider_output: JobAnalysisProviderOutput) -> JobAnalysisProposal:
        """Apply deterministic cross-field cleanup without making the proposal authoritative."""

        required_keys = {skill.casefold() for skill in provider_output.requirements.required_skills}
        preferred = [
            skill
            for skill in provider_output.requirements.preferred_skills
            if skill.casefold() not in required_keys
        ]
        requirements = JobRequirements(
            alternate_titles=provider_output.requirements.alternate_titles,
            required_skills=provider_output.requirements.required_skills,
            preferred_skills=preferred,
            locations=provider_output.requirements.locations,
            min_years_experience=provider_output.requirements.min_years_experience,
            seniority=provider_output.requirements.seniority,
            employment_type=provider_output.requirements.employment_type,
            work_arrangement=provider_output.requirements.work_arrangement,
        )

        questions: list[SuggestedScreeningQuestion] = []
        seen_keys: set[str] = set()
        for question in provider_output.suggested_screening_questions:
            if question.key in seen_keys:
                continue
            seen_keys.add(question.key)
            questions.append(question)

        return JobAnalysisProposal(
            suggested_title=provider_output.suggested_title,
            requirements=requirements,
            suggested_screening_questions=questions,
        )
