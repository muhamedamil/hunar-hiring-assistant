"""Explicit Module 5 contracts for preparation, frozen outreach, and dispatch."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.schemas import ScreeningQuestion, ScreeningQuestionCreate

OUTREACH_ACTION: Final[Literal["Voice screening outreach"]] = "Voice screening outreach"


class OutreachReadiness(StrEnum):
    """Derived execution readiness; it is never persisted as lifecycle state."""

    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    STALE = "STALE"


class OutreachScreeningQuestionDraft(ScreeningQuestionCreate):
    """Validated per-outreach question plus optional exact Job provenance."""

    source_job_question_id: UUID | None = None


class OutreachScreeningQuestion(OutreachScreeningQuestionDraft):
    """Frozen outreach question with server-owned identity for future answers."""

    id: UUID


class PrepareOutreachRequest(BaseModel):
    """Browser command containing no upstream-authoritative identifiers or contact."""

    model_config = ConfigDict(extra="forbid")
    preparation_token: str = Field(min_length=64, max_length=64)
    screening_questions: list[OutreachScreeningQuestionDraft] = Field(min_length=1, max_length=10)


class OutreachPreparationResponse(BaseModel):
    """Recruiter preparation view with masked contact and exact Job defaults."""

    model_config = ConfigDict(extra="forbid")
    job_candidate_id: UUID
    candidate_id: UUID
    candidate_name: str
    job_id: UUID
    role: str
    definition_version: int
    masked_phone: str | None
    default_screening_questions: list[OutreachScreeningQuestionDraft]
    preparation_token: str
    requested_action: Literal["Voice screening outreach"] = OUTREACH_ACTION
    can_prepare: bool
    blockers: list[str]


class OutreachRequestResponse(BaseModel):
    """Public immutable request view that never reveals its full phone snapshot."""

    model_config = ConfigDict(extra="forbid")
    id: UUID
    job_candidate_id: UUID
    decision_match_id: UUID
    candidate_name: str
    candidate_location: str | None
    masked_phone: str
    screening_questions: list[OutreachScreeningQuestion]
    screening_context_hash: str
    requested_action: Literal["Voice screening outreach"] = OUTREACH_ACTION
    readiness: OutreachReadiness
    stale_reasons: list[str]
    created_at: datetime


class OutreachRequestListResponse(BaseModel):
    """Bounded recruiter-facing list of immutable outreach requests."""

    model_config = ConfigDict(extra="forbid")
    items: list[OutreachRequestResponse]
    limit: int
    offset: int


class OutreachDispatchSnapshot(BaseModel):
    """Exact authoritative execution context reserved for future Module 6."""

    model_config = ConfigDict(extra="forbid")
    outreach_request_id: UUID
    job_candidate_id: UUID
    job_id: UUID
    candidate_id: UUID
    decision_match_id: UUID
    definition_version: int
    phone_e164: str
    screening_questions: list[OutreachScreeningQuestion]


class OutreachResultContext(BaseModel):
    """Narrow historical question context independent of current upstream readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    outreach_request_id: UUID
    screening_questions: list[OutreachScreeningQuestion]


def drafts_from_job_questions(
    questions: list[ScreeningQuestion],
) -> list[OutreachScreeningQuestionDraft]:
    """Map exact approved Job questions to editable outreach drafts with provenance."""

    return [
        OutreachScreeningQuestionDraft(
            source_job_question_id=question.id, **question.model_dump(mode="python", exclude={"id"})
        )
        for question in questions
    ]
