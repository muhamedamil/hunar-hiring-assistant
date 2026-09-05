"""State-machine tests for Module 1 JobService without requiring a live database."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.jobs.errors import (
    JobAlreadyReadyError,
    JobNotEditableError,
    JobNotReadyError,
    JobRevisionConflictError,
    ScreeningQuestionIdentityError,
)
from app.jobs.models import Job, JobDefinitionVersion
from app.jobs.schemas import (
    JobCreateRequest,
    JobDefinitionEdit,
    ScreeningAnswerType,
    ScreeningQuestionCreate,
    ScreeningQuestionEdit,
)
from app.jobs.service import JobService


class FakeSession:
    """Small transaction facade sufficient for deterministic service-unit testing."""

    def begin(self):  # type: ignore[no-untyped-def]
        return nullcontext()

    def flush(self) -> None:
        return None


class FakeJobRepository:
    """In-memory repository preserving Job/snapshot identity across service calls."""

    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}
        self.snapshots: dict[tuple[UUID, int], JobDefinitionVersion] = {}

    def create(self, session: Any, job: Job) -> Job:
        del session
        job.id = uuid4()
        now = datetime.now(UTC)
        job.created_at = now
        job.updated_at = now
        self.jobs[job.id] = job
        return job

    def get_by_id(self, session: Any, job_id: UUID) -> Job | None:
        del session
        return self.jobs.get(job_id)

    def get_for_update(self, session: Any, job_id: UUID) -> Job | None:
        del session
        return self.jobs.get(job_id)

    def list(self, session: Any, *, status, limit: int, offset: int):  # type: ignore[no-untyped-def]
        del session
        values = list(self.jobs.values())
        if status is not None:
            values = [job for job in values if job.status == status.value]
        return values[offset : offset + limit]

    def insert_definition_version(
        self, session: Any, snapshot: JobDefinitionVersion
    ) -> JobDefinitionVersion:
        del session
        snapshot.id = uuid4()
        snapshot.created_at = datetime.now(UTC)
        self.snapshots[(snapshot.job_id, snapshot.version)] = snapshot
        return snapshot

    def get_definition_version(
        self, session: Any, *, job_id: UUID, version: int
    ) -> JobDefinitionVersion | None:
        del session
        return self.snapshots.get((job_id, version))


def question(*, question_id: UUID | None = None, key: str = "interest") -> ScreeningQuestionEdit:
    return ScreeningQuestionEdit(
        id=question_id,
        key=key,
        prompt="Are you interested in this role?",
        answer_type=ScreeningAnswerType.YES_NO,
    )


def definition(*, questions: list[ScreeningQuestionEdit]) -> JobDefinitionEdit:
    return JobDefinitionEdit(
        title="Senior Python Engineer",
        company_name="Hunar.ai",
        description="Build reliable Python APIs for an AI hiring platform.",
        requirements={"required_skills": ["Python", "FastAPI"]},
        screening_questions=questions,
    )


def create_service() -> tuple[JobService, FakeJobRepository]:
    repository = FakeJobRepository()
    service = JobService(FakeSession(), repository)  # type: ignore[arg-type]
    return service, repository


def create_draft(service: JobService):  # type: ignore[no-untyped-def]
    return service.create_draft(
        JobCreateRequest(
            title="Senior Python Engineer",
            company_name="Hunar.ai",
            description="Build reliable Python APIs for an AI hiring platform.",
            requirements={"required_skills": ["Python"]},
            screening_questions=[
                ScreeningQuestionCreate(
                    key="interest",
                    prompt="Are you interested in this role?",
                    answer_type=ScreeningAnswerType.YES_NO,
                )
            ],
        )
    )


def test_create_is_draft_revision_zero_with_server_question_id() -> None:
    service, _ = create_service()
    created = create_draft(service)

    assert created.status.value == "draft"
    assert created.revision == 0
    assert created.approved_version is None
    assert created.screening_questions[0].id


def test_save_draft_preserves_existing_question_identity_and_increments_revision() -> None:
    service, _ = create_service()
    created = create_draft(service)
    existing_id = created.screening_questions[0].id

    saved = service.save_draft(
        created.id,
        expected_revision=0,
        definition=definition(questions=[question(question_id=existing_id)]),
    )

    assert saved.revision == 1
    assert saved.screening_questions[0].id == existing_id


def test_stale_revision_does_not_overwrite() -> None:
    service, _ = create_service()
    created = create_draft(service)
    existing_id = created.screening_questions[0].id

    service.save_draft(
        created.id,
        expected_revision=0,
        definition=definition(questions=[question(question_id=existing_id)]),
    )

    with pytest.raises(JobRevisionConflictError):
        service.save_draft(
            created.id,
            expected_revision=0,
            definition=definition(questions=[question(question_id=existing_id)]),
        )


def test_ready_snapshot_is_immutable_across_reopen_edit_and_reapprove() -> None:
    service, repository = create_service()
    created = create_draft(service)
    question_id = created.screening_questions[0].id

    ready_v1 = service.mark_ready(
        created.id,
        expected_revision=0,
        definition=definition(questions=[question(question_id=question_id)]),
    )
    assert ready_v1.approved_version == 1
    snapshot_v1 = repository.snapshots[(created.id, 1)]
    assert snapshot_v1.requirements["required_skills"] == ["Python", "FastAPI"]

    reopened = service.reopen(created.id, expected_revision=1)
    assert reopened.status.value == "draft"
    assert reopened.approved_version == 1

    edited_definition = definition(questions=[question(question_id=question_id)])
    edited_definition.requirements.required_skills = ["Python", "FastAPI", "PostgreSQL"]
    saved = service.save_draft(
        created.id,
        expected_revision=2,
        definition=edited_definition,
    )
    assert repository.snapshots[(created.id, 1)].requirements["required_skills"] == [
        "Python",
        "FastAPI",
    ]

    ready_v2 = service.mark_ready(
        created.id,
        expected_revision=saved.revision,
        definition=edited_definition,
    )
    assert ready_v2.approved_version == 2
    assert repository.snapshots[(created.id, 1)].requirements["required_skills"] == [
        "Python",
        "FastAPI",
    ]
    assert repository.snapshots[(created.id, 2)].requirements["required_skills"] == [
        "Python",
        "FastAPI",
        "PostgreSQL",
    ]


def test_ready_job_cannot_be_edited_or_marked_ready_twice() -> None:
    service, _ = create_service()
    created = create_draft(service)
    question_id = created.screening_questions[0].id
    ready = service.mark_ready(
        created.id,
        expected_revision=0,
        definition=definition(questions=[question(question_id=question_id)]),
    )

    with pytest.raises(JobNotEditableError):
        service.save_draft(
            created.id,
            expected_revision=ready.revision,
            definition=definition(questions=[question(question_id=question_id)]),
        )
    with pytest.raises(JobAlreadyReadyError):
        service.mark_ready(
            created.id,
            expected_revision=ready.revision,
            definition=definition(questions=[question(question_id=question_id)]),
        )


def test_draft_blocks_new_downstream_work_even_with_prior_approved_version() -> None:
    service, _ = create_service()
    created = create_draft(service)
    question_id = created.screening_questions[0].id
    ready = service.mark_ready(
        created.id,
        expected_revision=0,
        definition=definition(questions=[question(question_id=question_id)]),
    )
    approved = service.require_ready_definition(created.id)
    assert approved.version == 1

    service.reopen(created.id, expected_revision=ready.revision)
    with pytest.raises(JobNotReadyError):
        service.require_ready_definition(created.id)


def test_unknown_question_id_is_rejected() -> None:
    service, _ = create_service()
    created = create_draft(service)

    with pytest.raises(ScreeningQuestionIdentityError) as exc_info:
        service.save_draft(
            created.id,
            expected_revision=0,
            definition=definition(questions=[question(question_id=uuid4())]),
        )
    assert exc_info.value.code == "SCREENING_QUESTION_ID_UNKNOWN"


def test_duplicate_question_key_uses_stable_domain_error() -> None:
    service, _ = create_service()
    created = create_draft(service)

    with pytest.raises(ScreeningQuestionIdentityError) as exc_info:
        service.save_draft(
            created.id,
            expected_revision=0,
            definition=definition(
                questions=[question(key="interest"), question(key="interest")]
            ),
        )
    assert exc_info.value.code == "SCREENING_QUESTION_KEY_DUPLICATE"
