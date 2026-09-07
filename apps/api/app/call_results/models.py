"""ORM mappings for terminal call truth and immutable Module 5 question answers."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class VoiceCallResult(Base):
    """One terminal provider observation per immutable Module 6 execution."""

    __tablename__ = "voice_call_results"
    __table_args__ = (
        UniqueConstraint("voice_call_execution_id", name="uq_voice_call_results_execution"),
        UniqueConstraint("provider_call_id", name="uq_voice_call_results_provider_call"),
        CheckConstraint(
            "provider_status in ('COMPLETED','NOT_CONNECTED','FAILED','CANCELLED')",
            name="ck_voice_call_results_provider_status",
        ),
        CheckConstraint(
            "lifecycle_status in ('COMPLETED','NOT_CONNECTED','FAILED','CANCELLED')",
            name="ck_voice_call_results_lifecycle",
        ),
        CheckConstraint(
            "screening_result_state in ('available','unavailable','invalid')",
            name="ck_voice_call_results_state",
        ),
        CheckConstraint(
            "answered_by is null or answered_by in ('HUMAN','MACHINE','UNKNOWN')",
            name="ck_voice_call_results_answered_by",
        ),
        CheckConstraint(
            "conversation_outcome is null or conversation_outcome in "
            "('completed','partial','not_interested','wrong_person','not_available',"
            "'disconnected','other')",
            name="ck_voice_call_results_outcome",
        ),
        CheckConstraint(
            "candidate_interest is null or candidate_interest in "
            "('interested','not_interested','unclear')",
            name="ck_voice_call_results_interest",
        ),
        CheckConstraint(
            "duration_seconds is null or duration_seconds >= 0",
            name="ck_voice_call_results_duration",
        ),
        CheckConstraint(
            "started_at is null or ended_at is null or ended_at >= started_at",
            name="ck_voice_call_results_timing",
        ),
        CheckConstraint(
            "screening_result_state <> 'available' or "
            "(lifecycle_status = 'COMPLETED' and answered_by = 'HUMAN' and "
            "conversation_outcome is not null and candidate_interest is not null and "
            "result_failure_code is null)",
            name="ck_voice_call_results_available",
        ),
        CheckConstraint(
            "lifecycle_status = 'COMPLETED' or "
            "(screening_result_state = 'unavailable' and conversation_outcome is null and "
            "candidate_interest is null)",
            name="ck_voice_call_results_unavailable_lifecycle",
        ),
        CheckConstraint(
            "answered_by is null or answered_by = 'HUMAN' or "
            "screening_result_state <> 'available'",
            name="ck_voice_call_results_nonhuman",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    voice_call_execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voice_call_executions.id"), nullable=False
    )
    provider_call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provider_status: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False)
    answered_by: Mapped[str | None] = mapped_column(Text)
    screening_result_state: Mapped[str] = mapped_column(Text, nullable=False)
    result_failure_code: Mapped[str | None] = mapped_column(Text)
    conversation_outcome: Mapped[str | None] = mapped_column(Text)
    candidate_interest: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answers: Mapped[list["VoiceScreeningAnswer"]] = relationship(
        back_populates="result", order_by="VoiceScreeningAnswer.position"
    )


class VoiceScreeningAnswer(Base):
    """Immutable normalized answer linked to an exact historical outreach question UUID."""

    __tablename__ = "voice_screening_answers"
    __table_args__ = (
        UniqueConstraint(
            "voice_call_result_id", "position", name="uq_voice_screening_answers_position"
        ),
        UniqueConstraint(
            "voice_call_result_id",
            "outreach_question_id",
            name="uq_voice_screening_answers_question",
        ),
        CheckConstraint("position between 1 and 10", name="ck_voice_screening_answers_position"),
        CheckConstraint(
            "answer_state in ('answered','no_clear_answer','not_asked')",
            name="ck_voice_screening_answers_state",
        ),
        CheckConstraint(
            "(answer_state = 'answered' and nullif(btrim(answer_text), '') is not null) or "
            "(answer_state in ('no_clear_answer','not_asked') and answer_text is null)",
            name="ck_voice_screening_answers_text",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    voice_call_result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voice_call_results.id"), nullable=False
    )
    outreach_question_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    answer_state: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    result: Mapped[VoiceCallResult] = relationship(back_populates="answers")
