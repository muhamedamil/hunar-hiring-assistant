"""Module 6 authority, transaction topology, retries, worker and API behavioral tests."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_hunar_provider import AGENT_ID, agent_payload, provider, response_payload

from app.core.config import Settings
from app.core.retry import AmbiguousWorkError, PermanentWorkError, RetryableWorkError
from app.integrations.hunar.schemas import HunarLanguage, HunarTimezone
from app.jobs.schemas import JobRequirements
from app.main import create_app
from app.outreach.schemas import OutreachDispatchSnapshot, OutreachScreeningQuestion
from app.voice_calls.dependencies import get_voice_call_service
from app.voice_calls.errors import VoiceCallError
from app.voice_calls.repository import VoiceCallRepository
from app.voice_calls.service import VoiceCallService
from app.voice_calls.workers import VoiceCallWorkHandlers
from app.work_items.models import WorkItem


class Session:
    def __init__(self):
        self.active = False
        self.items = []
        self.fail_commit = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        assert not self.active

    @contextmanager
    def begin(self):
        assert not self.active
        self.active = True
        try:
            yield self
            if self.fail_commit:
                self.fail_commit = False
                raise RuntimeError("synthetic commit uncertainty")
        finally:
            self.active = False

    def in_transaction(self):
        return self.active

    def flush(self):
        assert self.active

    def execute(self, statement):
        return SimpleNamespace(scalars=lambda: self.items)


class Repository(VoiceCallRepository):
    def __init__(self):
        self.rows = {}

    def get_execution(self, session, execution_id):
        assert session.active
        return self.rows.get(execution_id)

    get_execution_for_update = get_execution

    def get_for_outreach(self, session, outreach_id):
        assert session.active
        return next((r for r in self.rows.values() if r.outreach_request_id == outreach_id), None)

    def insert_execution(self, session, row):
        assert session.active
        existing = self.get_for_outreach(session, row.outreach_request_id)
        if existing:
            return existing, False
        row.created_at = row.updated_at = datetime.now(UTC)
        self.rows[row.id] = row
        return row, True


@pytest.fixture()
def context(monkeypatch):
    session = Session()
    repository = Repository()
    calls = []
    state = {
        "stale": False,
        "failure": None,
        "response": None,
        "get_failure": None,
        "active_work": None,
        "name": "Controlled Candidate",
    }
    snapshot = OutreachDispatchSnapshot(
        outreach_request_id=uuid4(),
        job_candidate_id=uuid4(),
        job_id=uuid4(),
        candidate_id=uuid4(),
        decision_match_id=uuid4(),
        definition_version=3,
        phone_e164="+12025550123",
        screening_questions=[
            OutreachScreeningQuestion(
                id=uuid4(),
                key="interest",
                prompt="Are you interested in this role?",
                answer_type="yes_no",
                required=True,
            )
        ],
    )

    def dispatch(_service, actual_id):
        assert session.active
        assert actual_id == snapshot.outreach_request_id
        if state["stale"]:
            raise VoiceCallError("OUTREACH_NOT_DISPATCHABLE")
        return snapshot

    monkeypatch.setattr(
        "app.voice_calls.service.OutreachService.lock_dispatchable_outreach", dispatch
    )

    def definition(_service, job_id, version):
        assert session.active and job_id == snapshot.job_id and version == 3
        return SimpleNamespace(
            title="Engineer",
            requirements=JobRequirements(
                required_skills=["Python"], locations=["London"], min_years_experience=0
            ),
            screening_questions=["MUST NEVER BE USED"],
        )

    monkeypatch.setattr("app.voice_calls.service.JobService.get_definition_version", definition)

    def summaries(_service, ids):
        assert session.active and ids == {snapshot.candidate_id}
        return {
            snapshot.candidate_id: SimpleNamespace(
                full_name=state["name"], phone_e164="+12025550999"
            )
        }

    monkeypatch.setattr("app.voice_calls.service.CandidateService.get_summaries_by_ids", summaries)
    work = []

    def enqueue(_service, actual_session, command):
        assert actual_session.active
        work.append(command)

    monkeypatch.setattr("app.voice_calls.service.WorkItemService.enqueue", enqueue)
    monkeypatch.setattr(
        "app.voice_calls.service.WorkItemRepository.get_active_by_dedupe_key",
        lambda *_: state["active_work"],
    )

    def handle(request):
        assert not session.active, "Provider HTTP entered a DB transaction"
        calls.append(request)
        if request.method == "GET":
            if state["get_failure"]:
                return httpx.Response(state["get_failure"], json={})
            return httpx.Response(200, json=agent_payload())
        if isinstance(state["failure"], Exception):
            raise state["failure"]
        if state["failure"]:
            return httpx.Response(state["failure"], json={})
        row = next(iter(repository.rows.values()))
        from app.integrations.hunar.schemas import HunarCallCreateCommand

        cmd = HunarCallCreateCommand.model_validate(row.provider_payload_snapshot)
        return httpx.Response(200, json=state["response"] or response_payload(cmd))

    client = provider(handle)
    settings = Settings(
        database_url="postgresql://test",
        hunar_screening_agent_ids_json=('{"ENGLISH":"' + str(AGENT_ID) + '"}'),
    )
    service = VoiceCallService(session, settings=settings, provider=client, repository=repository)
    handlers = VoiceCallWorkHandlers(
        session_factory=lambda: session, settings=settings, provider=client, repository=repository
    )
    yield SimpleNamespace(
        session=session,
        repository=repository,
        service=service,
        handlers=handlers,
        state=state,
        snapshot=snapshot,
        work=work,
        calls=calls,
        provider=client,
    )
    client.close()


def start(c):
    result = c.service.create_execution(
        c.snapshot.outreach_request_id,
        language=HunarLanguage.ENGLISH,
        timezone=HunarTimezone.ASIA_KOLKATA,
    )
    return c.repository.rows[result.id]


def item(row, attempt=1):
    return WorkItem(
        id=uuid4(),
        entity_id=row.id,
        entity_type="voice_call_execution",
        work_type="hunar_voice_call_dispatch",
        attempt_count=attempt,
        max_attempts=3,
        status="running",
        locked_at=datetime.now(UTC),
        locked_by="test-worker",
    )


@pytest.mark.parametrize("origin", ["manual", "apollo"])
def test_both_origins_use_same_frozen_module5_topology(context, origin):
    # Candidate origin is intentionally not available to the service seam.
    c = context
    row = start(c)
    payload = row.provider_payload_snapshot
    assert payload["mobile_number"] == c.snapshot.phone_e164
    assert payload["mobile_number"] != "+12025550999"
    assert "MUST NEVER BE USED" not in str(payload)
    assert "Question 1\nKey: interest" in payload["custom_data"]["screening_plan"]
    assert "Minimum experience: 0 years" in payload["custom_data"]["role_context"]
    assert start(c).id == row.id
    assert len(c.work) == 1
    work = c.work[0]
    assert (
        work.work_type,
        work.entity_type,
        work.entity_id,
        work.dedupe_key,
        work.max_attempts,
    ) == (
        "hunar_voice_call_dispatch",
        "voice_call_execution",
        row.id,
        f"hunar-voice-call:{row.id}",
        3,
    )
    assert work.payload == {}
    c.handlers.handle_dispatch(item(row))
    assert row.status == "submitted" and row.provider_call_id and row.submitted_at
    projection = c.service.get_execution(row.id).model_dump(mode="json")
    assert (
        not {"provider_payload_snapshot", "phone", "callee_name", "mobile_number"}
        & projection.keys()
    )
    assert "Controlled Candidate" not in str(projection)
    assert [r.method for r in c.calls] == ["GET", "GET", "GET", "POST"]


@pytest.mark.parametrize(
    "status,retryable",
    [(429, True), (500, True), (502, True), (200, True), (401, False), (404, False), (400, False)],
)
def test_create_preflight_failure_never_creates_execution(context, status, retryable):
    c = context
    c.state["get_failure"] = status
    with pytest.raises(VoiceCallError) as caught:
        start(c)
    assert caught.value.code == (
        "HUNAR_PREFLIGHT_RETRYABLE" if retryable else "HUNAR_CONFIGURATION_FAILURE"
    )
    assert not c.repository.rows and not c.work


def test_options_never_gets_agent_and_unconfigured_language_rejected(context):
    c = context
    assert c.service.get_options().languages == [HunarLanguage.ENGLISH]
    assert not c.calls and not c.session.active
    with pytest.raises(VoiceCallError):
        c.service.create_execution(
            c.snapshot.outreach_request_id,
            language=HunarLanguage.HINDI,
            timezone=HunarTimezone.ASIA_KOLKATA,
        )
    assert not c.calls and not c.repository.rows


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, "failed"),
        (401, "failed"),
        (402, "failed"),
        (404, "failed"),
        (422, "failed"),
        (429, "queued"),
        (500, "unknown"),
        (502, "unknown"),
        (503, "unknown"),
        (504, "unknown"),
        (403, "unknown"),
        (408, "unknown"),
    ],
)
def test_post_http_certainty_matrix(context, status, expected):
    c = context
    row = start(c)
    c.state["failure"] = status
    error = {
        "failed": PermanentWorkError,
        "unknown": AmbiguousWorkError,
        "queued": RetryableWorkError,
    }[expected]
    with pytest.raises(error):
        c.handlers.handle_dispatch(item(row))
    assert row.status == expected
    assert len([r for r in c.calls if r.method == "POST"]) == 1


@pytest.mark.parametrize(
    "error,safe",
    [
        (httpx.ConnectError, True),
        (httpx.ConnectTimeout, True),
        (httpx.ReadTimeout, False),
        (httpx.WriteTimeout, False),
        (httpx.RemoteProtocolError, False),
        (RuntimeError, False),
    ],
)
def test_post_transport_certainty_matrix(context, error, safe):
    c = context
    row = start(c)
    c.state["failure"] = error("synthetic")
    with pytest.raises(RetryableWorkError if safe else AmbiguousWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == ("queued" if safe else "unknown")


@pytest.mark.parametrize("failure", [429, httpx.ConnectError("synthetic")])
def test_safe_retry_exact_payload_and_exhaustion(context, failure):
    c = context
    row = start(c)
    frozen = deepcopy(row.provider_payload_snapshot)
    c.state["failure"] = failure
    for attempt in (1, 2):
        with pytest.raises(RetryableWorkError):
            c.handlers.handle_dispatch(item(row, attempt))
        assert row.status == "queued"
    with pytest.raises(PermanentWorkError):
        c.handlers.handle_dispatch(item(row, 3))
    assert row.status == "failed" and row.failure_code == "HUNAR_ATTEMPTS_EXHAUSTED"
    import json

    assert all(json.loads(r.content) == frozen for r in c.calls if r.method == "POST")


@pytest.mark.parametrize(
    "status,retryable", [(429, True), (500, True), (200, True), (401, False), (404, False)]
)
def test_worker_read_only_preflight_classification(context, status, retryable):
    c = context
    row = start(c)
    c.state["get_failure"] = status
    with pytest.raises(RetryableWorkError if retryable else PermanentWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == ("queued" if retryable else "failed")
    assert all(r.method == "GET" for r in c.calls)
    if retryable:
        with pytest.raises(PermanentWorkError):
            c.handlers.handle_dispatch(item(row, 3))
        assert row.status == "failed"


def test_worker_revalidates_module5_before_preflight_or_post(context):
    c = context
    row = start(c)
    c.state["stale"] = True
    c.handlers.handle_dispatch(item(row))
    assert row.status == "failed" and row.failure_code == "OUTREACH_NOT_DISPATCHABLE"
    assert len(c.calls) == 1


def test_unknown_salvages_id_and_cannot_replay_or_retry(context):
    c = context
    row = start(c)
    call_id = uuid4()
    c.state["response"] = {"id": str(call_id), "status": "SCHEDULED"}
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == "unknown" and row.provider_call_id == call_id
    assert row.provider_initial_status == "SCHEDULED" and row.submitted_at is None
    before = len(c.calls)
    c.handlers.handle_dispatch(item(row))
    with pytest.raises(VoiceCallError):
        c.service.retry_failed_execution(row.id)
    assert len(c.calls) == before


def test_failed_retry_frozen_inputs_and_active_queue_race(context):
    c = context
    row = start(c)
    frozen = deepcopy(row.provider_payload_snapshot)
    c.state["failure"] = 402
    with pytest.raises(PermanentWorkError):
        c.handlers.handle_dispatch(item(row))
    c.state["active_work"] = item(row)
    with pytest.raises(VoiceCallError) as caught:
        c.service.retry_failed_execution(row.id)
    assert caught.value.code == "VOICE_CALL_WORK_STILL_ACTIVE" and row.status == "failed"
    c.state["active_work"] = None
    c.state["name"] = "Changed after creation"
    c.service.retry_failed_execution(row.id)
    assert row.status == "queued" and row.provider_payload_snapshot == frozen
    assert len(c.work) == 2 and c.work[0].dedupe_key == c.work[1].dedupe_key
    c.state["failure"] = None
    c.handlers.handle_dispatch(item(row))
    assert row.status == "submitted"


@pytest.mark.parametrize("status", ["queued", "submitted", "unknown", "failed"])
def test_unknown_queue_reconciliation_preserves_terminal_domain(context, status):
    c = context
    row = start(c)
    row.status = status
    work = item(row)
    work.status = "unknown"
    work.last_error_code = "WORKER_LEASE_EXPIRED"
    c.session.items = [work]
    count = c.handlers.reconcile_unknown_work()
    assert row.status == ("unknown" if status == "queued" else status)
    assert count == int(status == "queued")


def test_expired_lease_prevents_post(context):
    c = context
    row = start(c)
    work = item(row)
    work.locked_at -= timedelta(hours=1)
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(work)
    assert row.status == "unknown" and all(r.method == "GET" for r in c.calls)


def test_acceptance_persistence_uncertainty_preserves_submitted_if_commit_happened(
    context, monkeypatch
):
    c = context
    row = start(c)
    original = c.repository.mark_submitted

    def uncertain(*args):
        original(*args)
        c.session.fail_commit = True
        return True

    monkeypatch.setattr(c.repository, "mark_submitted", uncertain)
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == "submitted" and row.provider_call_id


def test_unknown_persistence_failure_still_raises_ambiguous(context, monkeypatch):
    c = context
    row = start(c)
    c.state["failure"] = 500
    monkeypatch.setattr(
        c.repository, "mark_unknown", Mock(side_effect=RuntimeError("DB unavailable"))
    )
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == "queued"


def test_api_exact_routes_202_validation_and_projection(context):
    c = context
    app = create_app()
    app.dependency_overrides[get_voice_call_service] = lambda: c.service
    with TestClient(app) as client:
        options = client.get("/api/v1/voice-screening/options")
        assert options.status_code == 200 and not c.calls
        base = f"/api/v1/outreach-requests/{c.snapshot.outreach_request_id}"
        assert client.get(base + "/voice-call-execution").json() is None
        payload = {"language": "ENGLISH", "timezone": "Asia/Kolkata"}
        assert (
            client.post(
                base + "/voice-call-executions", json={**payload, "phone": "private"}
            ).status_code
            == 422
        )
        response = client.post(base + "/voice-call-executions", json=payload)
        assert response.status_code == 202
        row = next(iter(c.repository.rows.values()))
        assert "provider_payload_snapshot" not in response.json()
        assert client.get(f"/api/v1/voice-call-executions/{row.id}").status_code == 200
        row.status = "unknown"
        assert client.post(f"/api/v1/voice-call-executions/{row.id}/retry").status_code == 409
        row.status = "failed"
        assert client.post(f"/api/v1/voice-call-executions/{row.id}/retry").status_code == 202


@pytest.mark.parametrize(
    "failure,attempt,expected",
    [(429, 1, "retry_scheduled"), (429, 3, "failed"), (500, 1, "unknown")],
)
def test_real_runner_domain_queue_convergence(context, monkeypatch, failure, attempt, expected):
    from test_work_item_state_machine import FakeRepository, _fake_session_scope

    from app.worker.registry import WorkHandlerRegistry
    from app.worker.runner import WorkerRunner

    c = context
    row = start(c)
    c.state["failure"] = failure
    registry = WorkHandlerRegistry()
    registry.register("hunar_voice_call_dispatch", c.handlers.handle_dispatch)
    queue = FakeRepository(item(row, attempt))
    _fake_session_scope(monkeypatch)
    runner = WorkerRunner(
        registry=registry,
        repository=queue,
        settings=Settings(database_url="postgresql://test"),
        worker_id="test",
    )
    assert runner.process_one()
    assert queue.outcome[0].value == expected
    assert (
        row.status
        == {"retry_scheduled": "queued", "failed": "failed", "unknown": "unknown"}[expected]
    )


def test_composition_registers_both_domains_and_single_reconciler(context, monkeypatch):
    import app.worker.main as composition

    sourcing = Mock()
    voice = Mock()
    monkeypatch.setattr(composition, "build_handlers", lambda: sourcing)
    monkeypatch.setattr(composition, "build_voice_handlers", lambda: voice)
    monkeypatch.setattr(
        composition, "get_settings", lambda: Settings(database_url="postgresql://test")
    )
    runner = Mock()

    def build_runner(**kwargs):
        registry = kwargs["registry"]
        assert registry.get("apollo_people_enrichment") == sourcing.handle_people_enrichment
        assert registry.get("apollo_enrichment_poll") == sourcing.handle_enrichment_poll
        assert registry.get("hunar_voice_call_dispatch") == voice.handle_dispatch
        kwargs["after_stale_recovery"]()
        return runner

    monkeypatch.setattr(composition, "WorkerRunner", build_runner)
    composition.main()
    sourcing.reconcile_unknown_work.assert_called_once()
    voice.reconcile_unknown_work.assert_called_once()


def test_late_acceptance_after_lease_expiry_retains_identity(context, monkeypatch):
    c = context
    row = start(c)
    work = item(row)
    original = c.provider.create_call

    def late(command):
        result = original(command)
        work.locked_at -= timedelta(hours=1)
        return result

    monkeypatch.setattr(c.provider, "create_call", late)
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(work)
    assert row.status == "unknown" and row.provider_call_id and row.submitted_at is None


def test_rejected_retry_preflight_and_upstream_leave_frozen_failed(context):
    c = context
    row = start(c)
    row.status = "failed"
    frozen = deepcopy(row.provider_payload_snapshot)
    c.state["get_failure"] = 500
    with pytest.raises(VoiceCallError):
        c.service.retry_failed_execution(row.id)
    assert row.status == "failed"
    c.state["get_failure"] = None
    c.state["stale"] = True
    with pytest.raises(VoiceCallError):
        c.service.retry_failed_execution(row.id)
    assert row.status == "failed" and row.provider_payload_snapshot == frozen
    assert len(c.work) == 1


def test_contract_drift_blocks_create_and_worker_without_post(context, monkeypatch):
    from app.integrations.hunar.schemas import HunarAgentDetail

    c = context
    original = c.provider.get_agent
    bad = HunarAgentDetail.model_validate({**agent_payload(), "agent_prompt": "drifted"})
    monkeypatch.setattr(c.provider, "get_agent", lambda _: bad)
    with pytest.raises(VoiceCallError):
        start(c)
    assert not c.repository.rows and not c.work
    monkeypatch.setattr(c.provider, "get_agent", original)
    row = start(c)
    monkeypatch.setattr(c.provider, "get_agent", lambda _: bad)
    with pytest.raises(PermanentWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == "failed" and all(r.method == "GET" for r in c.calls)


def test_retry_rechecks_status_after_read_only_preflight(context, monkeypatch):
    c = context
    row = start(c)
    row.status = "failed"
    original = c.provider.get_agent

    def concurrent(agent_id):
        assert not c.session.active
        row.status = "queued"
        return original(agent_id)

    monkeypatch.setattr(c.provider, "get_agent", concurrent)
    with pytest.raises(VoiceCallError):
        c.service.retry_failed_execution(row.id)
    assert len(c.work) == 1


def test_db_rollback_after_acceptance_retains_id_on_unknown(context, monkeypatch):
    c = context
    row = start(c)

    def fail_write(_row, _id, _status):
        raise RuntimeError("synthetic write failed before commit")

    monkeypatch.setattr(c.repository, "mark_submitted", fail_write)
    with pytest.raises(AmbiguousWorkError):
        c.handlers.handle_dispatch(item(row))
    assert row.status == "unknown" and row.provider_call_id and row.submitted_at is None


def test_screening_plan_order_options_and_role_context_are_deterministic(context):
    from app.jobs.schemas import JobRequirements
    from app.voice_calls.service import build_role_context, build_screening_plan

    first = context.snapshot.screening_questions[0]
    second = OutreachScreeningQuestion(
        id=uuid4(),
        key="availability",
        prompt="Which schedule can you work?",
        answer_type="choice",
        required=False,
        options=["Morning", "Evening"],
    )
    forward = build_screening_plan([first, second])
    assert forward.index(first.prompt) < forward.index(second.prompt)
    assert "Question 2\nKey: availability\nAnswer type: choice\nRequired: no" in forward
    assert "Options: Morning | Evening" in forward
    assert forward == build_screening_plan([first, second])
    reverse = build_screening_plan([second, first])
    assert reverse.index(second.prompt) < reverse.index(first.prompt)
    definition = SimpleNamespace(
        title="Engineer",
        requirements=JobRequirements(
            seniority=["senior"],
            locations=["London"],
            required_skills=["Python"],
            preferred_skills=["SQL"],
            min_years_experience=3,
            employment_type="full_time",
            work_arrangement="remote",
        ),
    )
    context_text = build_role_context(definition)
    assert context_text == build_role_context(definition)
    for text in [
        "Seniority: senior",
        "Locations: London",
        "Required skills: Python",
        "Preferred skills: SQL",
        "Minimum experience: 3 years",
        "Employment type: full_time",
        "Work arrangement: remote",
    ]:
        assert text in context_text


def test_provider_exception_details_never_leak_through_runner_logs(context, monkeypatch, caplog):
    from test_work_item_state_machine import FakeRepository, _fake_session_scope

    from app.worker.registry import WorkHandlerRegistry
    from app.worker.runner import WorkerRunner

    c = context
    row = start(c)
    c.state["failure"] = RuntimeError("private-payload +12025550123 Controlled Candidate")
    queue = FakeRepository(item(row))
    registry = WorkHandlerRegistry()
    registry.register("hunar_voice_call_dispatch", c.handlers.handle_dispatch)
    _fake_session_scope(monkeypatch)
    runner = WorkerRunner(
        registry=registry, repository=queue, settings=Settings(database_url="postgresql://test")
    )
    runner.process_one()
    assert queue.outcome[0].value == "unknown"
    assert "private-payload" not in caplog.text and "+12025550123" not in caplog.text
    assert "Controlled Candidate" not in str(queue.outcome)
