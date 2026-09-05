"""SQLAlchemy mappings for canonical Candidates and stable external identity links."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Candidate(Base):
    """Mutable global Candidate profile shared by manual and provider-sourced workflows."""

    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_candidates_revision"),
        CheckConstraint(
            "char_length(trim(full_name)) between 1 and 200",
            name="ck_candidates_full_name_length",
        ),
        CheckConstraint(
            "current_title is null or char_length(trim(current_title)) between 1 and 200",
            name="ck_candidates_current_title_length",
        ),
        CheckConstraint(
            "current_company is null or char_length(trim(current_company)) between 1 and 200",
            name="ck_candidates_current_company_length",
        ),
        CheckConstraint(
            "location is null or char_length(trim(location)) between 1 and 200",
            name="ck_candidates_location_length",
        ),
        CheckConstraint(
            "email is null or char_length(trim(email)) between 3 and 320",
            name="ck_candidates_email_length",
        ),
        CheckConstraint(
            "phone_e164 is null or phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'",
            name="ck_candidates_phone_e164",
        ),
        Index(
            "uq_candidates_email_ci",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email is not null"),
        ),
        Index(
            "uq_candidates_phone_e164",
            "phone_e164",
            unique=True,
            postgresql_where=text("phone_e164 is not null"),
        ),
        Index("ix_candidates_updated", text("updated_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_title: Mapped[str | None] = mapped_column(String(200))
    current_company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CandidateExternalIdentity(Base):
    """Stable provider/person identifier attached to one canonical Candidate."""

    __tablename__ = "candidate_external_identities"
    __table_args__ = (
        CheckConstraint(
            "provider ~ '^[a-z][a-z0-9_]{1,39}$'",
            name="ck_candidate_external_identities_provider",
        ),
        CheckConstraint(
            "char_length(trim(external_person_id)) between 1 and 255",
            name="ck_candidate_external_identities_person_id_length",
        ),
        CheckConstraint(
            "profile_url is null or char_length(trim(profile_url)) between 1 and 1000",
            name="ck_candidate_external_identities_profile_url_length",
        ),
        UniqueConstraint(
            "provider",
            "external_person_id",
            name="uq_candidate_external_identities_provider_person",
        ),
        Index("ix_candidate_external_identities_candidate", "candidate_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_person_id: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
