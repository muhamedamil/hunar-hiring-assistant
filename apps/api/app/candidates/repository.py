"""Persistence primitives for canonical Candidates and external identity links."""

from __future__ import annotations

import builtins
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.candidates.models import Candidate, CandidateExternalIdentity


class CandidateRepository:
    """Perform Candidate persistence without owning transactions or identity decisions."""

    def create(self, session: Session, candidate: Candidate) -> Candidate:
        """Insert a Candidate and flush server-generated identifiers/timestamps."""

        session.add(candidate)
        session.flush()
        return candidate

    def get_by_id(self, session: Session, candidate_id: UUID) -> Candidate | None:
        """Return a Candidate by ID without locking it."""

        return session.get(Candidate, candidate_id)

    def get_for_update(self, session: Session, candidate_id: UUID) -> Candidate | None:
        """Lock and return a Candidate for a revision-protected mutation."""

        statement: Select[tuple[Candidate]] = (
            select(Candidate).where(Candidate.id == candidate_id).with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def list(
        self,
        session: Session,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[Candidate]:
        """Return Candidate summaries ordered by most recent mutation."""

        statement: Select[tuple[Candidate]] = select(Candidate)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Candidate.full_name.ilike(pattern, escape="\\"),
                    Candidate.current_title.ilike(pattern, escape="\\"),
                    Candidate.current_company.ilike(pattern, escape="\\"),
                    Candidate.location.ilike(pattern, escape="\\"),
                )
            )
        statement = statement.order_by(Candidate.updated_at.desc()).limit(limit).offset(offset)
        return list(session.execute(statement).scalars())

    def find_by_email(self, session: Session, email: str | None) -> Candidate | None:
        """Resolve one Candidate through case-insensitive canonical email identity."""

        if email is None:
            return None
        statement = select(Candidate).where(func.lower(Candidate.email) == email.casefold())
        return session.execute(statement).scalar_one_or_none()

    def find_by_phone(self, session: Session, phone_e164: str | None) -> Candidate | None:
        """Resolve one Candidate through canonical E.164 phone identity."""

        if phone_e164 is None:
            return None
        statement = select(Candidate).where(Candidate.phone_e164 == phone_e164)
        return session.execute(statement).scalar_one_or_none()

    def find_external_identity(
        self,
        session: Session,
        *,
        provider: str,
        external_person_id: str,
    ) -> CandidateExternalIdentity | None:
        """Return one stable provider identity link."""

        statement = select(CandidateExternalIdentity).where(
            CandidateExternalIdentity.provider == provider,
            CandidateExternalIdentity.external_person_id == external_person_id,
        )
        return session.execute(statement).scalar_one_or_none()

    def list_external_identities(
        self,
        session: Session,
        candidate_id: UUID,
    ) -> builtins.list[CandidateExternalIdentity]:
        """Return provider identities attached to a Candidate in creation order."""

        statement = (
            select(CandidateExternalIdentity)
            .where(CandidateExternalIdentity.candidate_id == candidate_id)
            .order_by(CandidateExternalIdentity.created_at.asc())
        )
        return list(session.execute(statement).scalars())

    def insert_external_identity(
        self,
        session: Session,
        identity: CandidateExternalIdentity,
    ) -> CandidateExternalIdentity:
        """Attach one new provider/person identity and flush generated fields."""

        session.add(identity)
        session.flush()
        return identity
