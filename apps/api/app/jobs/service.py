"""Business services and state invariants for Job & Screening Definition workflows."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.jobs.domain import assert_unique_screening_question_keys
from app.jobs.errors import (
    JobAlreadyDraftError,
    JobAlreadyReadyError,
    JobDefinitionIncompleteError,
    JobNotEditableError,
    JobNotFoundError,
    JobNotReadyError,
    JobRevisionConflictError,
    ScreeningQuestionIdentityError,
)
from app.jobs.models import Job, JobDefinitionVersion
from app.jobs.repository import JobRepository
from app.jobs.schemas import (
    ApprovedJobDefinition,
    JobCreateRequest,
    JobDefinitionEdit,
    JobListResponse,
    JobRequirements,
    JobResponse,
    JobStatus,
    JobSummaryResponse,
    ScreeningQuestion,
    ScreeningQuestionCreate,
    ScreeningQuestionEdit,
)


class JobService:
    """Own Job state transitions, optimistic concurrency, and approved snapshot creation."""

    def __init__(self, session: Session, repository: JobRepository | None = None) -> None:
        self._session = session
        self._repository = repository or JobRepository()

    def create_draft(self, command: JobCreateRequest) -> JobResponse:
        """Create a new DRAFT Job with server-owned screening-question identities."""

        assert_unique_screening_question_keys(command.screening_questions)
        questions = self._materialize_new_questions(command.screening_questions)
        now = datetime.now(UTC)
        job = Job(
            title=command.title,
            company_name=command.company_name,
            description=command.description,
            requirements=command.requirements.model_dump(mode="json"),
            screening_questions=[question.model_dump(mode="json") for question in questions],
            status=JobStatus.DRAFT.value,
            revision=0,
            approved_version=None,
            updated_at=now,
        )
        with self._session.begin():
            self._repository.create(self._session, job)
        return self._to_job_response(job)

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        limit: int,
        offset: int,
    ) -> JobListResponse:
        """List Jobs using a compact recruiter-facing projection."""

        jobs = self._repository.list(
            self._session,
            status=status,
            limit=limit,
            offset=offset,
        )
        return JobListResponse(
            items=[self._to_summary_response(job) for job in jobs],
            limit=limit,
            offset=offset,
        )

    def get_job(self, job_id: UUID) -> JobResponse:
        """Return the current mutable Job aggregate."""

        job = self._repository.get_by_id(self._session, job_id)
        if job is None:
            raise JobNotFoundError()
        return self._to_job_response(job)

    def save_draft(
        self,
        job_id: UUID,
        *,
        expected_revision: int,
        definition: JobDefinitionEdit,
    ) -> JobResponse:
        """Replace a DRAFT definition after checking the caller's revision token."""

        with self._session.begin():
            job = self._require_locked_job(job_id)
            self._assert_revision(job, expected_revision)
            if JobStatus(job.status) is not JobStatus.DRAFT:
                raise JobNotEditableError()

            assert_unique_screening_question_keys(definition.screening_questions)
            questions = self._reconcile_questions(job, definition.screening_questions)
            self._apply_definition(job, definition, questions)
            job.revision += 1
            job.updated_at = datetime.now(UTC)
            self._session.flush()

        return self._to_job_response(job)

    def mark_ready(
        self,
        job_id: UUID,
        *,
        expected_revision: int,
        definition: JobDefinitionEdit,
    ) -> JobResponse:
        """Atomically save the visible definition and create the next immutable snapshot."""

        with self._session.begin():
            job = self._require_locked_job(job_id)
            self._assert_revision(job, expected_revision)
            if JobStatus(job.status) is JobStatus.READY:
                raise JobAlreadyReadyError()

            assert_unique_screening_question_keys(definition.screening_questions)
            questions = self._reconcile_questions(job, definition.screening_questions)
            self._validate_ready_definition(questions)
            self._apply_definition(job, definition, questions)

            next_version = (job.approved_version or 0) + 1
            snapshot = JobDefinitionVersion(
                job_id=job.id,
                version=next_version,
                title=job.title,
                company_name=job.company_name,
                description=job.description,
                requirements=deepcopy(job.requirements),
                screening_questions=deepcopy(job.screening_questions),
            )
            self._repository.insert_definition_version(self._session, snapshot)

            job.status = JobStatus.READY.value
            job.approved_version = next_version
            job.revision += 1
            job.updated_at = datetime.now(UTC)
            self._session.flush()

        return self._to_job_response(job)

    def reopen(self, job_id: UUID, *, expected_revision: int) -> JobResponse:
        """Reopen a READY Job while preserving every immutable approved snapshot."""

        with self._session.begin():
            job = self._require_locked_job(job_id)
            self._assert_revision(job, expected_revision)
            if JobStatus(job.status) is JobStatus.DRAFT:
                raise JobAlreadyDraftError()

            job.status = JobStatus.DRAFT.value
            job.revision += 1
            job.updated_at = datetime.now(UTC)
            self._session.flush()

        return self._to_job_response(job)

    def lock_ready_definition_for_downstream_binding(
        self,
        job_id: UUID,
    ) -> ApprovedJobDefinition:
        """Lock a READY Job and return its approved snapshot for atomic downstream binding.

        The caller must already own the surrounding transaction. This method deliberately does
        not commit so downstream services can create their bound record before releasing the Job
        row lock.
        """

        job = self._require_locked_job(job_id)
        if JobStatus(job.status) is not JobStatus.READY or job.approved_version is None:
            raise JobNotReadyError()
        snapshot = self._repository.get_definition_version(
            self._session,
            job_id=job.id,
            version=job.approved_version,
        )
        if snapshot is None:
            raise RuntimeError("READY job references a missing approved definition snapshot")
        return self._to_approved_definition(snapshot)

    def require_ready_definition(self, job_id: UUID) -> ApprovedJobDefinition:
        """Return the current approved snapshot only when the Job is presently READY."""

        job = self._repository.get_by_id(self._session, job_id)
        if job is None:
            raise JobNotFoundError()
        if JobStatus(job.status) is not JobStatus.READY or job.approved_version is None:
            raise JobNotReadyError()
        snapshot = self._repository.get_definition_version(
            self._session,
            job_id=job.id,
            version=job.approved_version,
        )
        if snapshot is None:
            raise RuntimeError("READY job references a missing approved definition snapshot")
        return self._to_approved_definition(snapshot)

    def get_definition_version(self, job_id: UUID, version: int) -> ApprovedJobDefinition:
        """Return an immutable historical definition version for downstream evidence."""

        job = self._repository.get_by_id(self._session, job_id)
        if job is None:
            raise JobNotFoundError()
        snapshot = self._repository.get_definition_version(
            self._session,
            job_id=job_id,
            version=version,
        )
        if snapshot is None:
            raise JobNotFoundError()
        return self._to_approved_definition(snapshot)

    def _require_locked_job(self, job_id: UUID) -> Job:
        job = self._repository.get_for_update(self._session, job_id)
        if job is None:
            raise JobNotFoundError()
        return job

    @staticmethod
    def _assert_revision(job: Job, expected_revision: int) -> None:
        if job.revision != expected_revision:
            raise JobRevisionConflictError(current_revision=job.revision)

    @staticmethod
    def _validate_ready_definition(questions: list[ScreeningQuestion]) -> None:
        missing: list[str] = []
        if not questions:
            missing.append("screening_questions")
        if missing:
            raise JobDefinitionIncompleteError(missing=missing)

    @staticmethod
    def _materialize_new_questions(
        questions: list[ScreeningQuestionCreate],
    ) -> list[ScreeningQuestion]:
        return [
            ScreeningQuestion(id=uuid4(), **question.model_dump(mode="python"))
            for question in questions
        ]

    def _reconcile_questions(
        self,
        job: Job,
        incoming: list[ScreeningQuestionEdit],
    ) -> list[ScreeningQuestion]:
        existing = {
            question.id: question
            for question in self._parse_canonical_questions(job.screening_questions)
        }
        materialized: list[ScreeningQuestion] = []
        seen_ids: set[UUID] = set()

        for question in incoming:
            if question.id is None:
                question_id = uuid4()
            else:
                question_id = question.id
                if question_id in seen_ids:
                    raise ScreeningQuestionIdentityError(
                        code="SCREENING_QUESTION_ID_DUPLICATE",
                        message="Screening question IDs must be unique within a Job.",
                    )
                if question_id not in existing:
                    raise ScreeningQuestionIdentityError(
                        code="SCREENING_QUESTION_ID_UNKNOWN",
                        message="A screening question ID does not belong to this Job.",
                        details={"question_id": str(question_id)},
                    )
            seen_ids.add(question_id)
            materialized.append(
                ScreeningQuestion(
                    id=question_id,
                    key=question.key,
                    prompt=question.prompt,
                    answer_type=question.answer_type,
                    required=question.required,
                    options=question.options,
                )
            )

        return materialized

    @staticmethod
    def _apply_definition(
        job: Job,
        definition: JobDefinitionEdit,
        questions: list[ScreeningQuestion],
    ) -> None:
        job.title = definition.title
        job.company_name = definition.company_name
        job.description = definition.description
        job.requirements = definition.requirements.model_dump(mode="json")
        job.screening_questions = [question.model_dump(mode="json") for question in questions]

    @staticmethod
    def _parse_canonical_questions(raw: list[dict[str, object]]) -> list[ScreeningQuestion]:
        return [ScreeningQuestion.model_validate(question) for question in raw]

    @classmethod
    def _to_job_response(cls, job: Job) -> JobResponse:
        return JobResponse(
            id=job.id,
            title=job.title,
            company_name=job.company_name,
            description=job.description,
            requirements=JobRequirements.model_validate(job.requirements),
            screening_questions=cls._parse_canonical_questions(job.screening_questions),
            status=JobStatus(job.status),
            revision=job.revision,
            approved_version=job.approved_version,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _to_summary_response(job: Job) -> JobSummaryResponse:
        return JobSummaryResponse(
            id=job.id,
            title=job.title,
            company_name=job.company_name,
            status=JobStatus(job.status),
            revision=job.revision,
            approved_version=job.approved_version,
            updated_at=job.updated_at,
        )

    @classmethod
    def _to_approved_definition(cls, snapshot: JobDefinitionVersion) -> ApprovedJobDefinition:
        return ApprovedJobDefinition(
            id=snapshot.id,
            job_id=snapshot.job_id,
            version=snapshot.version,
            title=snapshot.title,
            company_name=snapshot.company_name,
            description=snapshot.description,
            requirements=JobRequirements.model_validate(snapshot.requirements),
            screening_questions=cls._parse_canonical_questions(snapshot.screening_questions),
            created_at=snapshot.created_at,
        )
