"""SQLAlchemy mappings for mutable Jobs and immutable approved definition snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.jobs.schemas import JobStatus


class Job(Base):
    """Mutable current Job aggregate; approved historical truth lives in snapshots."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status in ('draft','ready')", name="ck_jobs_status"),
        CheckConstraint("revision >= 0", name="ck_jobs_revision"),
        CheckConstraint(
            "approved_version is null or approved_version >= 1",
            name="ck_jobs_approved_version",
        ),
        CheckConstraint(
            "char_length(trim(title)) between 1 and 200",
            name="ck_jobs_title_length",
        ),
        CheckConstraint(
            "company_name is null or char_length(trim(company_name)) between 1 and 200",
            name="ck_jobs_company_length",
        ),
        CheckConstraint(
            "char_length(trim(description)) between 20 and 20000",
            name="ck_jobs_description_length",
        ),
        CheckConstraint(
            "jsonb_typeof(requirements) = 'object'",
            name="ck_jobs_requirements_object",
        ),
        CheckConstraint(
            "jsonb_typeof(screening_questions) = 'array'",
            name="ck_jobs_screening_questions_array",
        ),
        CheckConstraint(
            "status = 'draft' or approved_version is not null",
            name="ck_jobs_ready_has_approved_version",
        ),
        ForeignKeyConstraint(
            ["id", "approved_version"],
            ["job_definition_versions.job_id", "job_definition_versions.version"],
            name="fk_jobs_approved_definition",
            use_alter=True,
        ),
        Index("ix_jobs_status_updated", "status", text("updated_at DESC")),
        Index("ix_jobs_created", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    screening_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobStatus.DRAFT.value
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class JobDefinitionVersion(Base):
    """Immutable approved Job snapshot used as downstream business truth."""

    __tablename__ = "job_definition_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_job_definition_versions_job_version"),
        CheckConstraint("version >= 1", name="ck_job_definition_versions_version"),
        CheckConstraint(
            "char_length(trim(title)) between 1 and 200",
            name="ck_job_definition_versions_title_length",
        ),
        CheckConstraint(
            "company_name is null or char_length(trim(company_name)) between 1 and 200",
            name="ck_job_definition_versions_company_length",
        ),
        CheckConstraint(
            "char_length(trim(description)) between 20 and 20000",
            name="ck_job_definition_versions_description_length",
        ),
        CheckConstraint(
            "jsonb_typeof(requirements) = 'object'",
            name="ck_job_definition_versions_requirements_object",
        ),
        CheckConstraint(
            "jsonb_typeof(screening_questions) = 'array'",
            name="ck_job_definition_versions_questions_array",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    screening_questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
