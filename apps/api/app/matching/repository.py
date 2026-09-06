"""Persistence primitives for Candidate↔Job relations and immutable match history."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.matching.models import JobCandidate, JobCandidateMatch
from app.matching.schemas import MatchStatus, ShortlistStatus


class MatchingRepository:
    """Perform Module 4 persistence without owning transactions or provider calls."""

    def create_job_candidate(self, session: Session, relation: JobCandidate) -> JobCandidate:
        """Insert a stable Candidate↔Job relationship and flush its generated identifier."""

        session.add(relation)
        session.flush()
        return relation

    def get_job_candidate(self, session: Session, relation_id: UUID) -> JobCandidate | None:
        """Return one Candidate↔Job relationship without locking it."""

        return session.get(JobCandidate, relation_id)

    def get_job_candidate_for_update(
        self,
        session: Session,
        relation_id: UUID,
    ) -> JobCandidate | None:
        """Lock one Candidate↔Job relationship for a state transition."""

        statement: Select[tuple[JobCandidate]] = (
            select(JobCandidate).where(JobCandidate.id == relation_id).with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def find_job_candidate(
        self,
        session: Session,
        *,
        job_id: UUID,
        candidate_id: UUID,
    ) -> JobCandidate | None:
        """Return the one stable relationship for a Job and canonical Candidate."""

        statement = select(JobCandidate).where(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
        return session.execute(statement).scalar_one_or_none()

    def find_job_candidate_for_update(
        self,
        session: Session,
        *,
        job_id: UUID,
        candidate_id: UUID,
    ) -> JobCandidate | None:
        """Lock the stable relationship while selecting preferred sourcing evidence."""

        statement: Select[tuple[JobCandidate]] = (
            select(JobCandidate)
            .where(
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == candidate_id,
            )
            .with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def list_for_job(
        self,
        session: Session,
        *,
        job_id: UUID,
        shortlist_status: ShortlistStatus | None,
        limit: int,
        offset: int,
    ) -> list[JobCandidate]:
        """List Candidate↔Job relations in stable recruiter-review order."""

        statement = select(JobCandidate).where(JobCandidate.job_id == job_id)
        if shortlist_status is not None:
            statement = statement.where(JobCandidate.shortlist_status == shortlist_status.value)
        statement = statement.order_by(JobCandidate.updated_at.desc()).limit(limit).offset(offset)
        return list(session.execute(statement).scalars())

    def insert_match(self, session: Session, match: JobCandidateMatch) -> JobCandidateMatch:
        """Insert one match attempt and flush generated fields."""

        session.add(match)
        session.flush()
        return match

    def get_match(self, session: Session, match_id: UUID) -> JobCandidateMatch | None:
        """Return one match attempt without locking it."""

        return session.get(JobCandidateMatch, match_id)

    def get_match_for_update(
        self,
        session: Session,
        match_id: UUID,
    ) -> JobCandidateMatch | None:
        """Lock one in-flight match attempt for finalization."""

        statement: Select[tuple[JobCandidateMatch]] = (
            select(JobCandidateMatch)
            .where(JobCandidateMatch.id == match_id)
            .with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def find_active_analysis(
        self,
        session: Session,
        *,
        relation_id: UUID,
        analysis_key_hash: str,
    ) -> JobCandidateMatch | None:
        """Return the active equivalent semantic analysis, if one exists."""

        statement = select(JobCandidateMatch).where(
            JobCandidateMatch.job_candidate_id == relation_id,
            JobCandidateMatch.analysis_key_hash == analysis_key_hash,
            JobCandidateMatch.status == MatchStatus.ANALYZING.value,
        )
        return session.execute(statement).scalar_one_or_none()

    def find_cached_completed(
        self,
        session: Session,
        *,
        relation_id: UUID,
        analysis_key_hash: str,
        require_hybrid: bool,
    ) -> JobCandidateMatch | None:
        """Return the newest reusable completed evaluation for an exact analysis input."""

        statement = select(JobCandidateMatch).where(
            JobCandidateMatch.job_candidate_id == relation_id,
            JobCandidateMatch.analysis_key_hash == analysis_key_hash,
            JobCandidateMatch.status == MatchStatus.COMPLETED.value,
        )
        if require_hybrid:
            statement = statement.where(JobCandidateMatch.analysis_mode == "hybrid_gemini")
        statement = statement.order_by(JobCandidateMatch.created_at.desc()).limit(1)
        return session.execute(statement).scalar_one_or_none()

    def list_matches(
        self,
        session: Session,
        *,
        relation_id: UUID,
        limit: int,
        offset: int,
    ) -> list[JobCandidateMatch]:
        """Return immutable historical match attempts newest first."""

        statement = (
            select(JobCandidateMatch)
            .where(JobCandidateMatch.job_candidate_id == relation_id)
            .order_by(JobCandidateMatch.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(session.execute(statement).scalars())

    def list_matches_by_ids(
        self,
        session: Session,
        match_ids: set[UUID],
    ) -> dict[UUID, JobCandidateMatch]:
        """Return a mapping for a bounded set of match identifiers."""

        if not match_ids:
            return {}
        statement = select(JobCandidateMatch).where(JobCandidateMatch.id.in_(match_ids))
        matches = list(session.execute(statement).scalars())
        return {match.id: match for match in matches}

    def mark_stale_analysis_failed(
        self,
        session: Session,
        match: JobCandidateMatch,
        *,
        completed_at: datetime,
    ) -> None:
        """Close an abandoned in-flight analysis so an explicit retry can proceed."""

        match.status = MatchStatus.FAILED.value
        match.semantic_failure_code = "MATCH_ANALYSIS_STALE"
        match.completed_at = completed_at
        match.updated_at = completed_at
        session.flush()
