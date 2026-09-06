"""SQLAlchemy mappings for sourcing searches, provider evidence, and enrichments."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.sourcing.schemas import EnrichmentStatus, PhoneAvailability, SourcingRunStatus


class SourcingRun(Base):
    """Historical provider-search execution bound to one approved Job definition."""

    __tablename__ = "sourcing_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "definition_version"],
            ["job_definition_versions.job_id", "job_definition_versions.version"],
            name="fk_sourcing_runs_job_definition",
        ),
        CheckConstraint(
            "status in ('searching','completed','failed')",
            name="ck_sourcing_runs_status",
        ),
        CheckConstraint("definition_version >= 1", name="ck_sourcing_runs_definition_version"),
        CheckConstraint("result_limit between 1 and 50", name="ck_sourcing_runs_result_limit"),
        CheckConstraint("result_count >= 0", name="ck_sourcing_runs_result_count"),
        CheckConstraint(
            "result_count <= result_limit",
            name="ck_sourcing_runs_result_bound",
        ),
        CheckConstraint("attempt_count >= 1", name="ck_sourcing_runs_attempt_count"),
        CheckConstraint("search_generation >= 1", name="ck_sourcing_runs_search_generation"),
        Index("ix_sourcing_runs_job_created", "job_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SourcingRunStatus.SEARCHING.value
    )
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provider_query: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(80), nullable=False)
    result_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_total_matches: Mapped[int | None] = mapped_column(BigInteger)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    search_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SourcingResult(Base):
    """One normalized provider search hit retained as sourcing evidence only."""

    __tablename__ = "sourcing_results"
    __table_args__ = (
        UniqueConstraint(
            "sourcing_run_id",
            "provider_person_id",
            name="uq_sourcing_results_run_person",
        ),
        UniqueConstraint(
            "sourcing_run_id",
            "result_position",
            name="uq_sourcing_results_run_position",
        ),
        CheckConstraint("result_position >= 1", name="ck_sourcing_results_position"),
        CheckConstraint(
            "phone_availability in ('available','maybe','unavailable','unknown')",
            name="ck_sourcing_results_phone_availability",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sourcing_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcing_runs.id", ondelete="CASCADE"), nullable=False
    )
    provider_person_id: Mapped[str] = mapped_column(String(255), nullable=False)
    result_position: Mapped[int] = mapped_column(Integer, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(200))
    last_name_obfuscated: Mapped[str | None] = mapped_column(String(200))
    current_title: Mapped[str | None] = mapped_column(String(200))
    organization_name: Mapped[str | None] = mapped_column(String(200))
    email_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phone_availability: Mapped[str] = mapped_column(
        String(30), nullable=False, default=PhoneAvailability.UNKNOWN.value
    )
    provider_last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class SourcingEnrichment(Base):
    """One logical credit-aware enrichment operation for one sourcing result."""

    __tablename__ = "sourcing_enrichments"
    __table_args__ = (
        UniqueConstraint(
            "sourcing_result_id",
            name="uq_sourcing_enrichments_result",
        ),
        CheckConstraint(
            "status in ('pending','awaiting_phone','completed','not_found','failed',"
            "'unknown','conflict')",
            name="ck_sourcing_enrichments_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_sourcing_enrichments_attempt_count"),
        Index(
            "uq_sourcing_enrichments_provider_request",
            "provider_request_id",
            unique=True,
            postgresql_where=text("provider_request_id is not null"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sourcing_result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sourcing_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EnrichmentStatus.PENDING.value
    )
    candidate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id")
    )
    provider_request_id: Mapped[int | None] = mapped_column(BigInteger)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_consumed: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
