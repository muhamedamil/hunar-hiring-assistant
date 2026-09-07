"""SQLAlchemy mapping for immutable Module 5 outreach execution contexts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OutreachRequest(Base):
    """One immutable phone and screening snapshot confirmed by a recruiter."""

    __tablename__ = "outreach_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["decision_match_id", "job_candidate_id"],
            ["job_candidate_matches.id", "job_candidate_matches.job_candidate_id"],
            name="fk_outreach_requests_decision_match",
        ),
        UniqueConstraint(
            "job_candidate_id",
            "decision_match_id",
            "phone_e164_snapshot",
            "screening_context_hash",
            name="uq_outreach_requests_exact_context",
        ),
        CheckConstraint(
            "phone_e164_snapshot ~ '^\\+[1-9][0-9]{7,14}$'", name="ck_outreach_requests_phone_e164"
        ),
        CheckConstraint(
            "jsonb_typeof(screening_questions_snapshot) = 'array'",
            name="ck_outreach_requests_questions_array",
        ),
        CheckConstraint(
            "jsonb_array_length(screening_questions_snapshot) between 1 and 10",
            name="ck_outreach_requests_question_count",
        ),
        CheckConstraint(
            "char_length(screening_context_hash) = 64", name="ck_outreach_requests_hash_length"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_candidates.id"), nullable=False
    )
    decision_match_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    phone_e164_snapshot: Mapped[str] = mapped_column(String(16), nullable=False)
    screening_questions_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    screening_context_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
