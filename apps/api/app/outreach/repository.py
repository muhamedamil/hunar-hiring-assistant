"""Persistence primitives for immutable Module 5 outreach requests."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.outreach.models import OutreachRequest


class OutreachRepository:
    """Read and insert outreach snapshots without transactions or eligibility rules."""

    def insert(self, session: Session, request: OutreachRequest) -> OutreachRequest:
        """Insert one immutable request and flush generated database fields."""

        session.add(request)
        session.flush()
        return request

    def find_exact(
        self,
        session: Session,
        *,
        job_candidate_id: UUID,
        decision_match_id: UUID,
        phone_e164_snapshot: str,
        screening_context_hash: str,
    ) -> OutreachRequest | None:
        """Return the unique request for one exact authoritative context."""

        statement = select(OutreachRequest).where(
            OutreachRequest.job_candidate_id == job_candidate_id,
            OutreachRequest.decision_match_id == decision_match_id,
            OutreachRequest.phone_e164_snapshot == phone_e164_snapshot,
            OutreachRequest.screening_context_hash == screening_context_hash,
        )
        return session.execute(statement).scalar_one_or_none()

    def get(self, session: Session, request_id: UUID) -> OutreachRequest | None:
        """Return one immutable request by identifier."""

        return session.get(OutreachRequest, request_id)

    def list(self, session: Session, *, limit: int, offset: int) -> list[OutreachRequest]:
        """List immutable requests newest first with bounded offset pagination."""

        statement = (
            select(OutreachRequest)
            .order_by(OutreachRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(session.execute(statement).scalars())
