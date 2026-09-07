"""Module 5 service tests for idempotency, provenance, staleness, and dispatch."""

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.jobs.schemas import ScreeningQuestion
from app.matching.schemas import DownstreamOutreachShortlist
from app.outreach.errors import (
    OutreachPreparationStaleError,
    OutreachQuestionCountError,
    OutreachQuestionProvenanceError,
)
from app.outreach.models import OutreachRequest
from app.outreach.schemas import OutreachScreeningQuestionDraft
from app.outreach.service import OutreachService, preparation_state_fingerprint


class FakeSession:
    def begin(self):
        return nullcontext()

    def rollback(self) -> None:
        pass




class FakeDashboardRepository:
    def __init__(self, shortlist) -> None:
        self.shortlist = shortlist
        self.execution_id = None
        self.screening_state = None
        self.submission_status = None

    def get_outreach_projection(self, _session, _request_id):
        return SimpleNamespace(
            job_id=self.shortlist.job_id,
            job_title="Backend Engineer",
            job_definition_version=self.shortlist.definition_version,
            execution_id=self.execution_id,
            screening_state=self.screening_state,
            submission_status=self.submission_status,
        )


class FakeRepository:
    def __init__(self) -> None:
        self.rows: list[OutreachRequest] = []

    def find_exact(self, _session, **values):
        return next(
            (
                row
                for row in self.rows
                if all(getattr(row, key) == value for key, value in values.items())
            ),
            None,
        )

    def insert(self, _session, request):
        request.id = uuid4()
        request.created_at = datetime.now(UTC)
        self.rows.append(request)
        return request

    def get(self, _session, request_id):
        return next((row for row in self.rows if row.id == request_id), None)

    def list(self, _session, *, limit, offset):
        return self.rows[offset : offset + limit]


@pytest.fixture()
def context(monkeypatch):
    relation_id = uuid4()
    job_id = uuid4()
    candidate_id = uuid4()
    match_id = uuid4()
    source_id = uuid4()
    shortlist = DownstreamOutreachShortlist(
        job_candidate_id=relation_id,
        job_id=job_id,
        candidate_id=candidate_id,
        decision_match_id=match_id,
        definition_version=2,
    )
    question = ScreeningQuestion(
        id=source_id,
        key="interest",
        prompt="Why are you interested in this role?",
        answer_type="short_text",
        required=True,
        options=[],
    )
    definition = SimpleNamespace(title="Backend Engineer", screening_questions=[question])

    class FakeJobService:
        def __init__(self, _session) -> None:
            pass

        def get_definition_version(self, actual_job_id, version):
            assert actual_job_id == job_id
            assert version == 2
            return definition

    monkeypatch.setattr("app.outreach.service.JobService", FakeJobService)
    repository = FakeRepository()
    dashboard_repository = FakeDashboardRepository(shortlist)
    service = OutreachService(
        FakeSession(),
        repository=repository,
        dashboard_repository=dashboard_repository,
    )
    state = {"shortlist": shortlist, "phone": "+919876543210"}
    monkeypatch.setattr(
        service,
        "_lock_current_context",
        lambda _relation_id: (state["shortlist"], state["phone"]),
    )
    monkeypatch.setattr(
        service,
        "_candidate_display",
        lambda _relation_id: ("Aisha Khan", "Bengaluru"),
    )
    return SimpleNamespace(
        service=service,
        repository=repository,
        state=state,
        shortlist=shortlist,
        source_id=source_id,
        dashboard_repository=dashboard_repository,
    )


def confirmation(context, questions=None, token=None):
    shortlist = context.state["shortlist"]
    phone = context.state["phone"]
    current_token = preparation_state_fingerprint(
        job_candidate_id=shortlist.job_candidate_id,
        decision_match_id=shortlist.decision_match_id,
        definition_version=shortlist.definition_version,
        phone_e164=phone,
    )
    return context.service.prepare_outreach(
        shortlist.job_candidate_id,
        preparation_token=token or current_token,
        screening_questions=questions
        if questions is not None
        else [
            OutreachScreeningQuestionDraft(
                source_job_question_id=context.source_id,
                key="interest",
                prompt="Why are you interested in this role?",
                answer_type="short_text",
                required=True,
                options=[],
            )
        ],
    )


def test_duplicate_confirm_returns_one_request_and_stable_question_identity(context) -> None:
    first = confirmation(context)
    second = confirmation(context)
    assert first.id == second.id
    assert first.screening_questions[0].id == second.screening_questions[0].id
    assert len(context.repository.rows) == 1


def test_changed_question_order_creates_distinct_immutable_context(context) -> None:
    first = OutreachScreeningQuestionDraft(
        source_job_question_id=context.source_id,
        key="interest",
        prompt="Why are you interested in this role?",
        answer_type="short_text",
        required=True,
        options=[],
    )
    second = OutreachScreeningQuestionDraft(
        source_job_question_id=None,
        key="notice",
        prompt="What is your notice period?",
        answer_type="short_text",
        required=True,
        options=[],
    )
    one = confirmation(context, [first, second])
    two = confirmation(context, [second, first])
    assert one.id != two.id
    assert one.screening_context_hash != two.screening_context_hash
    assert len(context.repository.rows) == 2


def test_stale_preparation_and_invalid_provenance_are_rejected(context) -> None:
    with pytest.raises(OutreachPreparationStaleError):
        confirmation(context, token="0" * 64)
    invalid = OutreachScreeningQuestionDraft(
        source_job_question_id=uuid4(),
        key="interest",
        prompt="Why are you interested in this role?",
        answer_type="short_text",
        required=True,
        options=[],
    )
    with pytest.raises(OutreachQuestionProvenanceError):
        confirmation(context, [invalid])

    with pytest.raises(OutreachQuestionCountError):
        confirmation(context, [])


def test_phone_change_between_preparation_and_confirmation_is_stale(context) -> None:
    shortlist = context.state["shortlist"]
    reviewed_token = preparation_state_fingerprint(
        job_candidate_id=shortlist.job_candidate_id,
        decision_match_id=shortlist.decision_match_id,
        definition_version=shortlist.definition_version,
        phone_e164=context.state["phone"],
    )
    context.state["phone"] = "+919111111111"

    with pytest.raises(OutreachPreparationStaleError):
        confirmation(context, token=reviewed_token)


def test_phone_change_preserves_history_and_derives_stale(context) -> None:
    confirmed = confirmation(context)
    context.state["phone"] = "+919111111111"
    historical = context.service.get_outreach_request(confirmed.id)
    assert historical.readiness == "STALE"
    assert historical.stale_reasons == ["canonical_phone_changed"]
    assert len(context.repository.rows) == 1


def test_unchanged_phone_remains_ready_independent_of_candidate_revision(context) -> None:
    confirmed = confirmation(context)
    current = context.service.get_outreach_request(confirmed.id)
    assert current.readiness == "READY_FOR_EXECUTION"
    assert current.candidate_name == "Aisha Khan"
    assert current.candidate_location == "Bengaluru"


def test_new_current_decision_preserves_old_request_as_stale(context) -> None:
    confirmed = confirmation(context)
    context.state["shortlist"] = context.shortlist.model_copy(
        update={"decision_match_id": uuid4()}
    )

    historical = context.service.get_outreach_request(confirmed.id)

    assert historical.readiness == "STALE"
    assert historical.stale_reasons == ["decision_match_changed"]


def test_dispatch_snapshot_uses_exact_frozen_values(context, monkeypatch) -> None:
    confirmed = confirmation(context)

    class FakeMatchingService:
        def __init__(self, _session) -> None:
            pass

        def lock_current_shortlist_for_downstream_outreach(self, _relation_id):
            return context.shortlist

    monkeypatch.setattr("app.outreach.service.MatchingService", FakeMatchingService)
    snapshot = context.service.lock_dispatchable_outreach(confirmed.id)
    assert snapshot.phone_e164 == "+919876543210"
    assert snapshot.screening_questions == confirmed.screening_questions
    assert snapshot.decision_match_id == context.shortlist.decision_match_id


def test_outreach_read_projection_keeps_readiness_and_execution_state_separate(context) -> None:
    confirmed = confirmation(context)
    context.dashboard_repository.execution_id = uuid4()
    context.dashboard_repository.screening_state = "result_available"
    context.dashboard_repository.submission_status = "unknown"

    projected = context.service.get_outreach_request(confirmed.id)

    assert projected.readiness == "READY_FOR_EXECUTION"
    assert projected.job_title == "Backend Engineer"
    assert projected.job_definition_version == 2
    assert projected.screening_state == "result_available"
    assert projected.submission_status == "unknown"
