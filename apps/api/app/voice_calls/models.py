"""SQLAlchemy mapping mirrors the migration; migrations alone own schema creation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoiceCallExecution(Base):
    """One immutable execution input with guarded submission-certainty transitions."""

    __tablename__ = "voice_call_executions"
    __table_args__ = (
        UniqueConstraint("outreach_request_id", name="uq_voice_call_executions_outreach"),
        UniqueConstraint("provider_request_id", name="uq_voice_call_executions_request"),
        UniqueConstraint("provider_call_id", name="uq_voice_call_executions_call"),
        CheckConstraint(
            "status in ('queued','submitted','failed','unknown')",
            name="ck_voice_call_executions_status",
        ),
        CheckConstraint(
            "provider_request_id ~ '^[A-Za-z0-9_.-]{1,64}$'",
            name="ck_voice_call_executions_request_id",
        ),
        CheckConstraint(
            "jsonb_typeof(provider_payload_snapshot) = 'object'",
            name="ck_voice_call_executions_payload",
        ),
        CheckConstraint(
            "(status = 'submitted' and provider_call_id is not null and provider_initial"
            "_status is not null and submitted_at is not null) or (status in ('queued','"
            "failed') and provider_call_id is null and submitted_at is null) or (status "
            "= 'unknown' and submitted_at is null)",
            name="ck_voice_call_executions_submission",
        ),
        CheckConstraint(
            "language in ('ENGLISH','HINDI','TAMIL','TELUGU','KANNADA','MARATHI','MALAYA"
            "LAM','GUJARATI','BENGALI','TURKISH','ARABIC','SPANISH')",
            name="ck_voice_call_executions_language",
        ),
        CheckConstraint(
            "timezone in ('Asia/Kolkata','America/New_York','America/Los_Angeles','Ameri"
            "ca/Chicago','America/Denver','America/Detroit','America/Kentucky/Louisville"
            "','America/Kentucky/Monticello','America/Indiana/Indianapolis','America/Ind"
            "iana/Vincennes','America/Indiana/Winamac','America/Indiana/Marengo','Americ"
            "a/Indiana/Petersburg','America/Indiana/Vevay','America/Indiana/Tell_City','"
            "America/Indiana/Knox','America/Menominee','America/North_Dakota/Center','Am"
            "erica/North_Dakota/New_Salem','America/North_Dakota/Beulah','America/Boise'"
            ",'America/Phoenix','America/Anchorage','America/Juneau','America/Sitka','Am"
            "erica/Metlakatla','America/Yakutat','America/Nome','America/Adak','Pacific/"
            "Honolulu','Asia/Riyadh','Europe/London')",
            name="ck_voice_call_executions_timezone",
        ),
        CheckConstraint(
            "provider_initial_status in ('NOT_STARTED','SCHEDULED','INITIATED','RINGING'"
            ",'IN_PROGRESS','COMPLETED','NOT_CONNECTED','CANCELLED','FAILED')",
            name="ck_voice_call_executions_provider_initial_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    outreach_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("outreach_requests.id"), nullable=False
    )
    agent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_call_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    provider_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    agent_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    provider_initial_status: Mapped[str | None] = mapped_column(Text)
    failure_code: Mapped[str | None] = mapped_column(Text)
    provider_payload_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
