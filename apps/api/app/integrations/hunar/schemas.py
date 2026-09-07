"""Hunar External API v1 wire contracts; outbound fields are deliberately restricted."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


class HunarLanguage(StrEnum):
    """Exact documented VoiceCallLanguage values (2026-09-07)."""

    ENGLISH = "ENGLISH"
    HINDI = "HINDI"
    TAMIL = "TAMIL"
    TELUGU = "TELUGU"
    KANNADA = "KANNADA"
    MARATHI = "MARATHI"
    MALAYALAM = "MALAYALAM"
    GUJARATI = "GUJARATI"
    BENGALI = "BENGALI"
    TURKISH = "TURKISH"
    ARABIC = "ARABIC"
    SPANISH = "SPANISH"


class HunarTimezone(StrEnum):
    """Exact documented Timezone values (2026-09-07)."""

    ASIA_KOLKATA = "Asia/Kolkata"
    AMERICA_NEW_YORK = "America/New_York"
    AMERICA_LOS_ANGELES = "America/Los_Angeles"
    AMERICA_CHICAGO = "America/Chicago"
    AMERICA_DENVER = "America/Denver"
    AMERICA_DETROIT = "America/Detroit"
    AMERICA_KENTUCKY_LOUISVILLE = "America/Kentucky/Louisville"
    AMERICA_KENTUCKY_MONTICELLO = "America/Kentucky/Monticello"
    AMERICA_INDIANA_INDIANAPOLIS = "America/Indiana/Indianapolis"
    AMERICA_INDIANA_VINCENNES = "America/Indiana/Vincennes"
    AMERICA_INDIANA_WINAMAC = "America/Indiana/Winamac"
    AMERICA_INDIANA_MARENGO = "America/Indiana/Marengo"
    AMERICA_INDIANA_PETERSBURG = "America/Indiana/Petersburg"
    AMERICA_INDIANA_VEVAY = "America/Indiana/Vevay"
    AMERICA_INDIANA_TELL_CITY = "America/Indiana/Tell_City"
    AMERICA_INDIANA_KNOX = "America/Indiana/Knox"
    AMERICA_MENOMINEE = "America/Menominee"
    AMERICA_NORTH_DAKOTA_CENTER = "America/North_Dakota/Center"
    AMERICA_NORTH_DAKOTA_NEW_SALEM = "America/North_Dakota/New_Salem"
    AMERICA_NORTH_DAKOTA_BEULAH = "America/North_Dakota/Beulah"
    AMERICA_BOISE = "America/Boise"
    AMERICA_PHOENIX = "America/Phoenix"
    AMERICA_ANCHORAGE = "America/Anchorage"
    AMERICA_JUNEAU = "America/Juneau"
    AMERICA_SITKA = "America/Sitka"
    AMERICA_METLAKATLA = "America/Metlakatla"
    AMERICA_YAKUTAT = "America/Yakutat"
    AMERICA_NOME = "America/Nome"
    AMERICA_ADAK = "America/Adak"
    PACIFIC_HONOLULU = "Pacific/Honolulu"
    ASIA_RIYADH = "Asia/Riyadh"
    EUROPE_LONDON = "Europe/London"


class HunarVoicePersona(StrEnum):
    """Exact documented VoicePersona values (2026-09-07)."""

    NEHA = "NEHA"
    ROY = "ROY"
    ZOE = "ZOE"
    SAM = "SAM"
    MIRA = "MIRA"
    EESHA = "EESHA"


class HunarAgentStatus(StrEnum):
    """Exact documented AgentStatus values (2026-09-07)."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class HunarCallStatus(StrEnum):
    """Exact documented CallStatus values (2026-09-07)."""

    NOT_STARTED = "NOT_STARTED"
    SCHEDULED = "SCHEDULED"
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NOT_CONNECTED = "NOT_CONNECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class HunarLifecycleStatus(StrEnum):
    """Provider lifecycle values; Module 7 persists terminal members only."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    NOT_CONNECTED = "NOT_CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class HunarAnsweredBy(StrEnum):
    """Provider classification used to fail closed before accepting screening answers."""

    HUMAN = "HUMAN"
    MACHINE = "MACHINE"
    UNKNOWN = "UNKNOWN"


class HunarAgentDetail(BaseModel):
    """Required preflight evidence; unrelated provider display fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    id: UUID
    status: HunarAgentStatus
    language: HunarLanguage
    voice_persona: HunarVoicePersona
    persona_name: StrictStr
    custom_variables: list[StrictStr]
    agent_prompt: StrictStr
    objective: StrictStr | None
    introduction: StrictStr
    result_prompt: StrictStr | None
    result_schema: dict[str, object]


class HunarRetryConfig(BaseModel):
    """Explicitly disable provider redials regardless of organization defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    max_retry_count: Literal[0] = 0
    retry_interval_hours: Literal[0] = 0


class HunarCallbackConfig(BaseModel):
    """Only a genuinely configured HTTPS summary receiver may be sent."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    call_summary_callback_url: StrictStr = Field(max_length=2083)

    @field_validator("call_summary_callback_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Reject non-HTTPS, credential-bearing, or hostless callback URLs."""
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("Summary callback must be an HTTPS URL without credentials")
        return value


class HunarCallCreateCommand(BaseModel):
    """Frozen outbound payload; request_id is correlation, never idempotency."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    agent_id: UUID
    callee_name: StrictStr = Field(min_length=1)
    mobile_number: StrictStr = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    custom_data: dict[str, StrictStr]
    request_id: StrictStr = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    timezone: HunarTimezone
    retry_config: HunarRetryConfig
    callback_config: HunarCallbackConfig | None = None

    @model_validator(mode="after")
    def exact_custom_data(self) -> Self:
        """Prevent sourcing, scoring, contact or arbitrary custom-data leakage."""
        if set(self.custom_data) != {"job_role", "role_context", "screening_plan"}:
            raise ValueError("Custom data must have exactly the three screening variables")
        return self


class HunarCallCreateResponse(BaseModel):
    """Provider acceptance evidence; status is not local call-lifecycle truth."""

    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    id: UUID
    request_id: StrictStr
    status: HunarCallStatus
    callee_name: StrictStr
    mobile_number: StrictStr
    timezone: HunarTimezone


class HunarCallSummaryWebhook(BaseModel):
    """Authenticated call-summary fields used by Module 7; unrelated fields are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    event_type: Literal["call_summary"]
    call_id: UUID
    agent_id: UUID
    request_id: StrictStr = Field(min_length=1, max_length=64)
    to_number: StrictStr = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    status: HunarCallStatus
    lifecycle_status: HunarLifecycleStatus
    answered_by: HunarAnsweredBy | None = None
    max_retries: int
    retry_count: int
    retries_left: int
    next_retry_scheduled_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    timezone: HunarTimezone
    recording_url: StrictStr | None = None
    result: dict[str, object] | None = None


class HunarCallDetail(BaseModel):
    """Read-only detailed-call evidence normalized without persisting its raw response."""

    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)
    id: UUID
    agent_id: UUID
    request_id: StrictStr = Field(min_length=1, max_length=64)
    mobile_number: StrictStr = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    status: HunarCallStatus
    lifecycle_status: HunarLifecycleStatus
    answered_by: HunarAnsweredBy | None = None
    max_retries: int
    retry_count: int
    retries_left: int
    next_retry_scheduled_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    recording_url: StrictStr | None = None
    result: dict[str, object] | None = None
    timezone: HunarTimezone | None = None
