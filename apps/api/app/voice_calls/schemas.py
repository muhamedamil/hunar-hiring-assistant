"""Public Module 6 projections deliberately exclude Candidate PII and raw payloads."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.integrations.hunar.schemas import HunarCallStatus, HunarLanguage, HunarTimezone


class VoiceCallExecutionStatus(StrEnum):
    """Submission certainty, independent of Module 7 call lifecycle."""

    QUEUED = "queued"
    SUBMITTED = "submitted"
    FAILED = "failed"
    UNKNOWN = "unknown"


class VoiceScreeningOptionsResponse(BaseModel):
    """Locally configured language choices and provider-supported timezones."""

    languages: list[HunarLanguage]
    default_language: HunarLanguage
    timezones: list[HunarTimezone]
    default_timezone: HunarTimezone
    automatic_redials: Literal[False] = False


class VoiceCallExecutionCreateRequest(BaseModel):
    """Recruiter chooses language/timezone only; all other authority is upstream."""

    model_config = ConfigDict(extra="forbid")
    language: HunarLanguage
    timezone: HunarTimezone


class VoiceCallExecutionResponse(BaseModel):
    """Safe execution projection with provider identity but no phone/name/payload."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    outreach_request_id: UUID
    status: VoiceCallExecutionStatus
    language: HunarLanguage
    timezone: HunarTimezone
    agent_contract_version: str
    provider_call_id: UUID | None
    provider_initial_status: HunarCallStatus | None
    failure_code: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VoiceCallResultBinding(BaseModel):
    """Internal immutable execution identity exposed narrowly to Module 7."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    execution_id: UUID
    outreach_request_id: UUID
    execution_status: VoiceCallExecutionStatus
    agent_id: UUID
    language: HunarLanguage
    timezone: HunarTimezone
    agent_contract_version: str
    provider_request_id: str
    provider_call_id: UUID | None
    expected_mobile_number: str
