"""Persistence primitives for Module 3 sourcing runs, evidence, and enrichments."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.sourcing.models import SourcingEnrichment, SourcingResult, SourcingRun


class SourcingRepository:
    """Perform sourcing persistence without owning transactions or provider logic."""

    def create_run(self, session: Session, run: SourcingRun) -> SourcingRun:
        """Insert one sourcing run and flush its generated identifier."""

        session.add(run)
        session.flush()
        return run

    def get_run(self, session: Session, run_id: UUID) -> SourcingRun | None:
        """Return a sourcing run by identifier without locking it."""

        return session.get(SourcingRun, run_id)

    def get_run_for_update(self, session: Session, run_id: UUID) -> SourcingRun | None:
        """Lock and return a sourcing run for one lifecycle mutation."""

        statement: Select[tuple[SourcingRun]] = (
            select(SourcingRun).where(SourcingRun.id == run_id).with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def list_runs_for_job(self, session: Session, job_id: UUID) -> list[SourcingRun]:
        """Return sourcing history for a Job ordered newest first."""

        statement = (
            select(SourcingRun)
            .where(SourcingRun.job_id == job_id)
            .order_by(SourcingRun.created_at.desc())
        )
        return list(session.execute(statement).scalars())

    def insert_results(
        self,
        session: Session,
        results: list[SourcingResult],
    ) -> list[SourcingResult]:
        """Insert one fully validated provider page as normalized search evidence."""

        session.add_all(results)
        session.flush()
        return results

    def list_results(self, session: Session, run_id: UUID) -> list[SourcingResult]:
        """Return normalized search evidence in provider result order."""

        statement = (
            select(SourcingResult)
            .where(SourcingResult.sourcing_run_id == run_id)
            .order_by(SourcingResult.result_position.asc())
        )
        return list(session.execute(statement).scalars())

    def get_result(self, session: Session, result_id: UUID) -> SourcingResult | None:
        """Return one sourcing result without locking it."""

        return session.get(SourcingResult, result_id)

    def get_result_for_update(self, session: Session, result_id: UUID) -> SourcingResult | None:
        """Lock and return one sourcing result for Candidate attachment."""

        statement: Select[tuple[SourcingResult]] = (
            select(SourcingResult).where(SourcingResult.id == result_id).with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def create_enrichment(
        self,
        session: Session,
        enrichment: SourcingEnrichment,
    ) -> SourcingEnrichment:
        """Insert one logical enrichment operation and flush its identifier."""

        session.add(enrichment)
        session.flush()
        return enrichment

    def get_enrichment(
        self,
        session: Session,
        enrichment_id: UUID,
    ) -> SourcingEnrichment | None:
        """Return one sourcing enrichment without locking it."""

        return session.get(SourcingEnrichment, enrichment_id)

    def get_enrichment_for_update(
        self,
        session: Session,
        enrichment_id: UUID,
    ) -> SourcingEnrichment | None:
        """Lock one enrichment for request/finalization lifecycle mutation."""

        statement: Select[tuple[SourcingEnrichment]] = (
            select(SourcingEnrichment)
            .where(SourcingEnrichment.id == enrichment_id)
            .with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def get_enrichment_by_result(
        self,
        session: Session,
        result_id: UUID,
    ) -> SourcingEnrichment | None:
        """Return the single logical enrichment associated with a sourcing result."""

        statement = select(SourcingEnrichment).where(
            SourcingEnrichment.sourcing_result_id == result_id
        )
        return session.execute(statement).scalar_one_or_none()

    def find_enrichment_by_request_id(
        self,
        session: Session,
        request_id: int,
    ) -> SourcingEnrichment | None:
        """Resolve Apollo's signed 64-bit request ID to the owning enrichment."""

        statement = select(SourcingEnrichment).where(
            SourcingEnrichment.provider_request_id == request_id
        )
        return session.execute(statement).scalar_one_or_none()

    def list_enrichments_for_run(
        self,
        session: Session,
        run_id: UUID,
    ) -> list[SourcingEnrichment]:
        """Return enrichments associated with every result in one sourcing run."""

        statement = (
            select(SourcingEnrichment)
            .join(
                SourcingResult,
                SourcingResult.id == SourcingEnrichment.sourcing_result_id,
            )
            .where(SourcingResult.sourcing_run_id == run_id)
            .order_by(SourcingEnrichment.created_at.asc())
        )
        return list(session.execute(statement).scalars())
