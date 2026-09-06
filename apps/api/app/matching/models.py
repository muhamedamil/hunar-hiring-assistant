"""SQLAlchemy mappings for stable Candidate↔Job relations and versioned match evaluations."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.matching.schemas import JobCandidateSource, MatchStatus, ShortlistStatus


class JobCandidate(Base):
    """Stable Candidate↔Job relationship and current recruiter shortlist state."""

    __tablename__ = "job_candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_job_candidates_job_candidate"),
        UniqueConstraint(
            "id",
            "job_id",
            "candidate_id",
            name="uq_job_candidates_identity_tuple",
        ),
        CheckConstraint(
            "created_source in ('manual','sourcing')",
            name="ck_job_candidates_created_source",
        ),
        CheckConstraint(
            "created_source = 'manual' or preferred_sourcing_result_id is not null",
            name="ck_job_candidates_sourcing_has_source",
        ),
        CheckConstraint(
            "shortlist_status in ('reviewing','shortlisted','not_selected')",
            name="ck_job_candidates_shortlist_status",
        ),
        CheckConstraint("revision >= 0", name="ck_job_candidates_revision"),
        CheckConstraint(
            "(shortlist_status = 'reviewing' and decision_match_id is null) "
            "or (shortlist_status in ('shortlisted','not_selected') "
            "and decision_match_id is not null)",
            name="ck_job_candidates_decision_match_state",
        ),
        ForeignKeyConstraint(
            ["current_match_id", "id"],
            ["job_candidate_matches.id", "job_candidate_matches.job_candidate_id"],
            name="fk_job_candidates_current_match",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["decision_match_id", "id"],
            ["job_candidate_matches.id", "job_candidate_matches.job_candidate_id"],
            name="fk_job_candidates_decision_match",
            use_alter=True,
        ),
        Index(
            "ix_job_candidates_job_status_updated",
            "job_id",
            "shortlist_status",
            text("updated_at DESC"),
        ),
        Index("ix_job_candidates_candidate", "candidate_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False
    )
    created_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=JobCandidateSource.MANUAL.value
    )
    preferred_sourcing_result_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcing_results.id")
    )
    shortlist_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ShortlistStatus.REVIEWING.value
    )
    current_match_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_match_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class JobCandidateMatch(Base):
    """One historical match attempt; completed rows become immutable business evidence."""

    __tablename__ = "job_candidate_matches"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "job_candidate_id",
            name="uq_job_candidate_matches_relation_identity",
        ),
        ForeignKeyConstraint(
            ["job_candidate_id", "job_id", "candidate_id"],
            ["job_candidates.id", "job_candidates.job_id", "job_candidates.candidate_id"],
            name="fk_job_candidate_matches_relation",
        ),
        ForeignKeyConstraint(
            ["job_id", "definition_version"],
            ["job_definition_versions.job_id", "job_definition_versions.version"],
            name="fk_job_candidate_matches_job_definition",
        ),
        ForeignKeyConstraint(
            ["job_id", "source_definition_version"],
            ["job_definition_versions.job_id", "job_definition_versions.version"],
            name="fk_job_candidate_matches_source_definition",
        ),
        CheckConstraint("definition_version >= 1", name="ck_candidate_matches_definition"),
        CheckConstraint("candidate_revision >= 0", name="ck_candidate_matches_revision"),
        CheckConstraint(
            "source_definition_version is null or source_definition_version >= 1",
            name="ck_candidate_matches_source_definition",
        ),
        CheckConstraint(
            "(source_sourcing_result_id is null and source_sourcing_run_id is null "
            "and source_definition_version is null and source_evidence_version is null) "
            "or (source_sourcing_result_id is not null and source_sourcing_run_id is not null "
            "and source_definition_version is not null)",
            name="ck_candidate_matches_source_provenance",
        ),
        CheckConstraint(
            "char_length(input_hash) = 64 and char_length(analysis_key_hash) = 64",
            name="ck_candidate_matches_hash_length",
        ),
        CheckConstraint(
            "analysis_mode in ('deterministic','hybrid_gemini','deterministic_fallback')",
            name="ck_candidate_matches_analysis_mode",
        ),
        CheckConstraint(
            "status in ('analyzing','completed','failed')",
            name="ck_candidate_matches_status",
        ),
        CheckConstraint(
            "retry_after_seconds is null or retry_after_seconds >= 0",
            name="ck_candidate_matches_retry_after",
        ),
        CheckConstraint(
            "match_score is null or match_score between 0 and 100",
            name="ck_candidate_matches_score",
        ),
        CheckConstraint(
            "evidence_coverage is null or evidence_coverage between 0 and 100",
            name="ck_candidate_matches_coverage",
        ),
        CheckConstraint(
            "match_score is null or evidence_coverage is null or match_score <= evidence_coverage",
            name="ck_candidate_matches_score_within_coverage",
        ),
        CheckConstraint(
            "match_reasons is null or jsonb_typeof(match_reasons) = 'array'",
            name="ck_candidate_matches_reasons_array",
        ),
        CheckConstraint(
            "jsonb_typeof(input_snapshot) = 'object'",
            name="ck_candidate_matches_input_object",
        ),
        CheckConstraint(
            "(status = 'analyzing' and completed_at is null and match_score is null "
            "and evidence_coverage is null and match_reasons is null) "
            "or (status = 'completed' and completed_at is not null "
            "and match_score is not null and evidence_coverage is not null "
            "and match_reasons is not null) "
            "or (status = 'failed' and completed_at is not null)",
            name="ck_candidate_matches_completion_state",
        ),
        Index(
            "uq_candidate_matches_active_analysis",
            "job_candidate_id",
            "analysis_key_hash",
            unique=True,
            postgresql_where=text("status = 'analyzing'"),
        ),
        Index(
            "ix_candidate_matches_relation_created",
            "job_candidate_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sourcing_result_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcing_results.id")
    )
    source_sourcing_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sourcing_runs.id")
    )
    source_definition_version: Mapped[int | None] = mapped_column(Integer)
    source_evidence_version: Mapped[str | None] = mapped_column(String(80))
    candidate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    matcher_version: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=MatchStatus.ANALYZING.value
    )
    semantic_model: Mapped[str | None] = mapped_column(String(200))
    semantic_prompt_version: Mapped[str | None] = mapped_column(String(80))
    semantic_failure_code: Mapped[str | None] = mapped_column(String(120))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    match_score: Mapped[int | None] = mapped_column(Integer)
    evidence_coverage: Mapped[int | None] = mapped_column(Integer)
    match_reasons: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
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
