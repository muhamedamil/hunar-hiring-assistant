"""Disposable migrated PostgreSQL tests: real locks, uniqueness, immutability and queue state."""

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from test_hunar_provider import AGENT_ID, agent_payload, response_payload
from test_outreach_postgres import _confirm, _create_shortlisted_context

from app.core.config import Settings
from app.integrations.hunar.schemas import HunarCallCreateResponse, HunarLanguage, HunarTimezone
from app.voice_calls.models import VoiceCallExecution
from app.voice_calls.service import VoiceCallService
from app.voice_calls.workers import VoiceCallWorkHandlers
from app.work_items.repository import WorkItemRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason=("Set TEST_DATABASE_URL to a disposable PostgreSQL database migrated through Module 6"),
)


@pytest.fixture()
def db():
    url = os.environ["TEST_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "truncate table public.jobs, public.candidates, public.work_items "
                "restart identity cascade"
            )
        )
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    outreach = _confirm(factory, _create_shortlisted_context(factory))
    settings = Settings(
        database_url=url, hunar_screening_agent_ids_json=('{"ENGLISH":"' + str(AGENT_ID) + '"}')
    )
    from app.integrations.hunar.schemas import HunarAgentDetail

    class Provider:
        failure = None
        calls = []

        def get_agent(self, _agent_id):
            return HunarAgentDetail.model_validate(agent_payload())

        def create_call(self, command):
            self.calls.append(command.model_dump(mode="json", exclude_none=True))
            if self.failure:
                raise self.failure
            return HunarCallCreateResponse.model_validate(response_payload(command))

    provider = Provider()

    def start():
        with factory() as session:
            service = VoiceCallService(session, settings=settings, provider=provider)
            return service.create_execution(
                outreach.id, language=HunarLanguage.ENGLISH, timezone=HunarTimezone.ASIA_KOLKATA
            )

    yield factory, engine, start, provider, settings
    engine.dispose()


def test_concurrent_start_real_locks_and_active_dedupe(db):
    factory, engine, start, _, _ = db
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: start(), range(2)))
    assert results[0].id == results[1].id == start().id
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from voice_call_executions")).scalar_one() == 1
        row = conn.execute(
            text("select work_type,entity_type,dedupe_key,max_attempts,payload from work_items")
        ).one()
        assert row.work_type == "hunar_voice_call_dispatch"
        assert row.entity_type == "voice_call_execution"
        assert row.dedupe_key == f"hunar-voice-call:{results[0].id}"
        assert row.max_attempts == 3 and row.payload == {}


def test_sqlalchemy_migration_column_constraint_parity_and_rls(db):
    _, engine, start, _, _ = db
    start()
    inspector = inspect(engine)
    table = VoiceCallExecution.__table__
    columns = {c["name"]: c for c in inspector.get_columns(table.name)}
    assert columns.keys() == set(table.columns.keys())
    for col in table.columns:
        assert columns[col.name]["nullable"] == col.nullable
    from sqlalchemy import CheckConstraint, UniqueConstraint

    assert {c["name"] for c in inspector.get_check_constraints(table.name)} == {
        c.name for c in table.constraints if isinstance(c, CheckConstraint)
    }
    assert {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table.name)} == {
        tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)
    }
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "select relrowsecurity, "
                "has_table_privilege('anon','voice_call_executions','SELECT') as anon_read, "
                "has_table_privilege('authenticated','voice_call_executions','SELECT') "
                "as auth_read "
                "from pg_class where oid='voice_call_executions'::regclass"
            )
        ).one()
        assert row.relrowsecurity and not row.anon_read and not row.auth_read


@pytest.mark.parametrize(
    "column,value",
    [
        ("outreach_request_id", uuid4()),
        ("agent_id", uuid4()),
        ("language", "HINDI"),
        ("timezone", "Europe/London"),
        ("agent_contract_version", "changed"),
        ("provider_request_id", "changed"),
        ("provider_payload_snapshot", "{}"),
    ],
)
def test_each_input_column_immutable(db, column, value):
    _, engine, start, _, _ = db
    row = start()
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(
            text(f"update voice_call_executions set {column}=:value where id=:id"),
            {"value": value, "id": row.id},
        )


@pytest.mark.parametrize("status", ["submitted", "bogus"])
def test_invalid_status_or_missing_acceptance_fields_rejected(db, status):
    _, engine, start, _, _ = db
    row = start()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("update voice_call_executions set status=:status where id=:id"),
            {"status": status, "id": row.id},
        )


def test_unknown_retains_id_and_operational_transitions(db):
    _, engine, start, _, _ = db
    row = start()
    call_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "update voice_call_executions set status='failed', failure_code='TEST' where id=:id"
            ),
            {"id": row.id},
        )
        conn.execute(
            text(
                "update voice_call_executions set status='queued', failure_code=null where id=:id"
            ),
            {"id": row.id},
        )
        conn.execute(
            text(
                "update voice_call_executions set status='unknown',provider_call_id=:call,"
                "provider_initial_status='SCHEDULED' where id=:id"
            ),
            {"id": row.id, "call": call_id},
        )
        observed = conn.execute(
            text("select * from voice_call_executions where id=:id"), {"id": row.id}
        ).one()
        assert observed.provider_call_id == call_id and observed.submitted_at is None


def test_unique_outreach_request_and_call_ids(db):
    factory, engine, start, _, _ = db
    result = start()
    with factory() as session:
        original = session.get(VoiceCallExecution, result.id)
        values = {
            col.name: deepcopy(getattr(original, col.name))
            for col in VoiceCallExecution.__table__.columns
        }
    from app.outreach.models import OutreachRequest
    from app.outreach.service import OutreachService

    with factory() as session:
        with session.begin():
            request = session.get(OutreachRequest, result.outreach_request_id)
            relation_id = request.job_candidate_id
        service = OutreachService(session)
        preparation = service.get_preparation(relation_id)
        question = preparation.default_screening_questions[0].model_copy(
            update={"prompt": "What is your interest in this opportunity?"}
        )
        second_outreach = service.prepare_outreach(
            relation_id,
            preparation_token=preparation.preparation_token,
            screening_questions=[question],
        )
    # Each separate constraint is exercised without relying on earlier conflict ordering.
    for change in [
        dict(id=uuid4(), provider_request_id="hha-" + uuid4().hex),
        dict(id=uuid4(), outreach_request_id=second_outreach.id),
    ]:
        with pytest.raises(IntegrityError), factory.begin() as session:
            session.add(VoiceCallExecution(**{**values, **change}))
            session.flush()
    call_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("update voice_call_executions set status='unknown', provider_call_id=:id"),
            {"id": call_id},
        )
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(
            VoiceCallExecution(
                **{
                    **values,
                    "id": uuid4(),
                    "outreach_request_id": second_outreach.id,
                    "provider_request_id": "hha-" + uuid4().hex,
                    "status": "unknown",
                    "provider_call_id": call_id,
                }
            )
        )
        session.flush()


def test_stale_running_queue_reconciles_to_unknown(db):
    factory, _, start, provider, settings = db
    row = start()
    repo = WorkItemRepository()
    with factory.begin() as session:
        work = repo.claim_next(session, worker_id="stale")
        work.locked_at = datetime.now(UTC) - timedelta(hours=1)
    with factory.begin() as session:
        assert repo.recover_stale_running(session, lease_seconds=300) == 1
    handlers = VoiceCallWorkHandlers(session_factory=factory, provider=provider, settings=settings)
    assert handlers.reconcile_unknown_work() == 1
    with factory() as session:
        execution = session.get(VoiceCallExecution, row.id)
        assert execution.status == "unknown" and execution.failure_code == "WORKER_LEASE_EXPIRED"
    assert not provider.calls
