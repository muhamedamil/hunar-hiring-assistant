"""Persistence primitives for Jobs and immutable approved definition snapshots."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.jobs.models import Job, JobDefinitionVersion
from app.jobs.schemas import JobStatus


class JobRepository:
    """Repository that performs Job persistence without owning transactions or state rules."""

    def create(self, session: Session, job: Job) -> Job:
        """Insert a new mutable Job aggregate and flush its server-generated fields."""

        session.add(job)
        session.flush()
        return job

    def get_by_id(self, session: Session, job_id: UUID) -> Job | None:
        """Return a Job by identifier without locking it."""

        return session.get(Job, job_id)

    def get_for_update(self, session: Session, job_id: UUID) -> Job | None:
        """Lock and return a Job for a revision-protected mutation."""

        statement: Select[tuple[Job]] = (
            select(Job).where(Job.id == job_id).with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    def list(
        self,
        session: Session,
        *,
        status: JobStatus | None,
        limit: int,
        offset: int,
    ) -> list[Job]:
        """Return Jobs ordered by most recently updated first."""

        statement: Select[tuple[Job]] = select(Job)
        if status is not None:
            statement = statement.where(Job.status == status.value)
        statement = statement.order_by(Job.updated_at.desc()).limit(limit).offset(offset)
        return list(session.execute(statement).scalars())

    def insert_definition_version(
        self,
        session: Session,
        snapshot: JobDefinitionVersion,
    ) -> JobDefinitionVersion:
        """Insert one immutable approved definition snapshot."""

        session.add(snapshot)
        session.flush()
        return snapshot

    def get_definition_version(
        self,
        session: Session,
        *,
        job_id: UUID,
        version: int,
    ) -> JobDefinitionVersion | None:
        """Return a specific immutable approved definition snapshot."""

        statement = select(JobDefinitionVersion).where(
            JobDefinitionVersion.job_id == job_id,
            JobDefinitionVersion.version == version,
        )
        return session.execute(statement).scalar_one_or_none()
