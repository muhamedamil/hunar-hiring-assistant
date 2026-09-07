"""Persistence-only operations for Module 7; callers own transactions and interpretation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer


class CallResultRepository:
    """Read, lock, insert, and enrich result rows without provider or business decisions."""

    def get_result_for_execution(
        self, session: Session, execution_id: UUID
    ) -> VoiceCallResult | None:
        """Read one result and its ordered immutable answer set."""

        return session.execute(
            select(VoiceCallResult)
            .where(VoiceCallResult.voice_call_execution_id == execution_id)
            .options(selectinload(VoiceCallResult.answers))
        ).scalar_one_or_none()

    def get_result_for_update(self, session: Session, execution_id: UUID) -> VoiceCallResult | None:
        """Lock one result identity before semantic duplicate/enrichment handling."""

        return session.execute(
            select(VoiceCallResult)
            .where(VoiceCallResult.voice_call_execution_id == execution_id)
            .with_for_update()
            .options(selectinload(VoiceCallResult.answers))
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def get_by_provider_call_id(
        self, session: Session, provider_call_id: UUID
    ) -> VoiceCallResult | None:
        """Read the globally unique result bound to a provider call."""

        return session.execute(
            select(VoiceCallResult)
            .where(VoiceCallResult.provider_call_id == provider_call_id)
            .options(selectinload(VoiceCallResult.answers))
        ).scalar_one_or_none()

    def insert_result(self, session: Session, row: VoiceCallResult) -> tuple[VoiceCallResult, bool]:
        """Converge only the two declared Module 7 uniqueness races via a savepoint."""

        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row, True
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint not in {
                "uq_voice_call_results_execution",
                "uq_voice_call_results_provider_call",
            }:
                raise
            existing = self.get_result_for_update(session, row.voice_call_execution_id)
            if existing is None:
                existing = self.get_by_provider_call_id(session, row.provider_call_id)
            if existing is None:
                raise
            return existing, False

    def enrich_result(self, session: Session, row: VoiceCallResult) -> None:
        """Flush service-authorized monotonic changes so DB triggers remain final authority."""

        session.flush([row])

    def insert_answers(self, session: Session, answers: list[VoiceScreeningAnswer]) -> None:
        """Insert one complete mapped answer set; rows are immutable after flush."""

        session.add_all(answers)
        session.flush()

    def list_answers(self, session: Session, result_id: UUID) -> list[VoiceScreeningAnswer]:
        """Return immutable answers in exact Module 5 question order."""

        return list(
            session.execute(
                select(VoiceScreeningAnswer)
                .where(VoiceScreeningAnswer.voice_call_result_id == result_id)
                .order_by(VoiceScreeningAnswer.position)
            ).scalars()
        )
