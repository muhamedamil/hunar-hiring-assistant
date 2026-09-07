"""Module 7 evidence, versioned result parsing, and PII-safe public response contracts."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictStr

from app.call_results.errors import CallResultError
from app.integrations.hunar.schemas import (
    HunarAnsweredBy,
    HunarCallDetail,
    HunarCallStatus,
    HunarCallSummaryWebhook,
    HunarLifecycleStatus,
    HunarTimezone,
)
from app.voice_calls.agent_contract import RESULT_SCHEMA_JSON

TERMINAL_LIFECYCLES = frozenset(
    {
        HunarLifecycleStatus.COMPLETED,
        HunarLifecycleStatus.NOT_CONNECTED,
        HunarLifecycleStatus.FAILED,
        HunarLifecycleStatus.CANCELLED,
    }
)
TERMINAL_PROVIDER_STATUSES = frozenset(
    {
        HunarCallStatus.COMPLETED,
        HunarCallStatus.NOT_CONNECTED,
        HunarCallStatus.FAILED,
        HunarCallStatus.CANCELLED,
    }
)


class ScreeningResultState(StrEnum):
    """Whether structured Candidate screening evidence is safely consumable."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class ScreeningAnswerState(StrEnum):
    """Normalized factual state of one configured historical question."""

    ANSWERED = "answered"
    NO_CLEAR_ANSWER = "no_clear_answer"
    NOT_ASKED = "not_asked"


class ConversationOutcome(StrEnum):
    """Frozen v1 conversation outcomes; none is a hiring decision."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    NOT_INTERESTED = "not_interested"
    WRONG_PERSON = "wrong_person"
    NOT_AVAILABLE = "not_available"
    DISCONNECTED = "disconnected"
    OTHER = "other"


class CandidateInterest(StrEnum):
    """Frozen v1 factual interest labels, not matching or qualification state."""

    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    UNCLEAR = "unclear"


class ScreeningResultV1(BaseModel):
    """Exact strict result object frozen by the Module 6 English v1 agent contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    conversation_outcome: ConversationOutcome
    candidate_interest: CandidateInterest
    question_1_answer: StrictStr
    question_2_answer: StrictStr
    question_3_answer: StrictStr
    question_4_answer: StrictStr
    question_5_answer: StrictStr
    question_6_answer: StrictStr
    question_7_answer: StrictStr
    question_8_answer: StrictStr
    question_9_answer: StrictStr
    question_10_answer: StrictStr
    notes: StrictStr


class ScreeningResultContract(BaseModel):
    """Version resolver output tied to the immutable execution contract version."""

    model_config = ConfigDict(frozen=True)
    version: Literal["hunar_voice_screening_en_v1"]
    expected_keys: frozenset[str]

    def parse(self, value: object) -> ScreeningResultV1:
        """Validate without coercion or additional provider decision fields."""

        return ScreeningResultV1.model_validate(value)


def get_screening_result_contract(agent_contract_version: str) -> ScreeningResultContract:
    """Resolve only explicitly implemented historical schemas; unsupported versions fail closed."""

    if agent_contract_version != "hunar_voice_screening_en_v1":
        raise CallResultError("HUNAR_RESULT_CONTRACT_UNSUPPORTED")
    return ScreeningResultContract(
        version="hunar_voice_screening_en_v1",
        expected_keys=frozenset(json.loads(RESULT_SCHEMA_JSON)),
    )


class TerminalCallEvidence(BaseModel):
    """Provider-independent terminal evidence shared by webhook and GET recovery."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    provider_call_id: UUID
    provider_request_id: str
    agent_id: UUID
    mobile_number: str
    provider_status: HunarCallStatus
    lifecycle_status: HunarLifecycleStatus
    answered_by: HunarAnsweredBy | None
    max_retries: int
    retry_count: int
    retries_left: int
    next_retry_scheduled_at: datetime | None
    timezone: HunarTimezone | None
    duration_seconds: float | None
    started_at: datetime | None
    ended_at: datetime | None
    recording_url: str | None
    provider_result: dict[str, object] | None

    @classmethod
    def from_summary(cls, summary: HunarCallSummaryWebhook) -> TerminalCallEvidence:
        """Normalize authenticated summary evidence without provider HTTP."""

        return cls(
            provider_call_id=summary.call_id,
            provider_request_id=summary.request_id,
            agent_id=summary.agent_id,
            mobile_number=summary.to_number,
            provider_status=summary.status,
            lifecycle_status=summary.lifecycle_status,
            answered_by=summary.answered_by,
            max_retries=summary.max_retries,
            retry_count=summary.retry_count,
            retries_left=summary.retries_left,
            next_retry_scheduled_at=summary.next_retry_scheduled_at,
            timezone=summary.timezone,
            duration_seconds=summary.duration_seconds,
            started_at=summary.started_at,
            ended_at=summary.ended_at,
            recording_url=summary.recording_url,
            provider_result=summary.result,
        )

    @classmethod
    def from_detail(cls, detail: HunarCallDetail) -> TerminalCallEvidence:
        """Normalize one exact read-only detailed-call response."""

        return cls(
            provider_call_id=detail.id,
            provider_request_id=detail.request_id,
            agent_id=detail.agent_id,
            mobile_number=detail.mobile_number,
            provider_status=detail.status,
            lifecycle_status=detail.lifecycle_status,
            answered_by=detail.answered_by,
            max_retries=detail.max_retries,
            retry_count=detail.retry_count,
            retries_left=detail.retries_left,
            next_retry_scheduled_at=detail.next_retry_scheduled_at,
            timezone=detail.timezone,
            duration_seconds=detail.duration_seconds,
            started_at=detail.started_at,
            ended_at=detail.ended_at,
            recording_url=detail.recording_url,
            provider_result=detail.result,
        )


class VoiceScreeningAnswerResponse(BaseModel):
    """PII-minimized answer projection linked to immutable Module 5 question identity."""

    model_config = ConfigDict(from_attributes=True)
    outreach_question_id: UUID
    position: int
    answer_state: ScreeningAnswerState
    answer_text: str | None


class VoiceCallResultResponse(BaseModel):
    """Public terminal truth with only recording availability, never its provider URL."""

    id: UUID
    voice_call_execution_id: UUID
    provider_call_id: UUID
    provider_status: HunarCallStatus
    lifecycle_status: HunarLifecycleStatus
    answered_by: HunarAnsweredBy | None
    screening_result_state: ScreeningResultState
    result_failure_code: str | None
    conversation_outcome: ConversationOutcome | None
    candidate_interest: CandidateInterest | None
    notes: str | None
    duration_seconds: float | None
    started_at: datetime | None
    ended_at: datetime | None
    recording_available: bool
    observed_at: datetime
    updated_at: datetime
    answers: list[VoiceScreeningAnswerResponse]


class ReconciliationResponse(BaseModel):
    """Bounded outcome of one explicit read-only provider reconciliation."""

    state: Literal["already_finalized", "not_terminal", "finalized", "enriched"]
    result: VoiceCallResultResponse | None
