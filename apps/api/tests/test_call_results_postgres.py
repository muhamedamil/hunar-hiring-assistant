"""Disposable PostgreSQL qualification for Module 7 constraints, convergence, and independence."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, text
from sqlalchemy.exc import DBAPIError
from test_call_results import evidence, result_payload
from test_voice_calls_postgres import db as module6_db  # noqa: F401

from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer
from app.call_results.schemas import TerminalCallEvidence
from app.call_results.service import CallResultService

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a disposable PostgreSQL database migrated through Module 7",
)


@pytest.fixture(name="module6_database")
def module6_database_fixture(request):
    """Reuse the complete Module 6 execution fixture under a lint-safe local name."""

    return request.getfixturevalue("module6_db")


def load_evidence(factory, execution_id, call_id=None, **changes) -> TerminalCallEvidence:
    """Read only immutable Module 6 identity needed to construct provider evidence."""

    from app.voice_calls.models import VoiceCallExecution

    with factory() as session:
        row = session.get(VoiceCallExecution, execution_id)
        payload = row.provider_payload_snapshot
        return evidence(
            provider_call_id=call_id or uuid4(),
            provider_request_id=row.provider_request_id,
            agent_id=row.agent_id,
            mobile_number=payload["mobile_number"],
            timezone=row.timezone,
            provider_result=result_payload(),
            **changes,
        )


def test_module7_migration_orm_constraint_and_rls_parity(module6_database) -> None:
    _, engine, _, _, _ = module6_database
    inspector = inspect(engine)
    for table in (VoiceCallResult.__table__, VoiceScreeningAnswer.__table__):
        columns = {column["name"]: column for column in inspector.get_columns(table.name)}
        assert columns.keys() == set(table.columns.keys())
        assert {item["name"] for item in inspector.get_check_constraints(table.name)} == {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints(table.name)
        } == {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
    with engine.connect() as connection:
        for table_name in ("voice_call_results", "voice_screening_answers"):
            row = connection.execute(
                text(
                    "select relrowsecurity, "
                    f"has_table_privilege('anon','{table_name}','SELECT') anon_read, "
                    f"has_table_privilege('authenticated','{table_name}','SELECT') auth_read "
                    f"from pg_class where oid='{table_name}'::regclass"
                )
            ).one()
            assert row.relrowsecurity and not row.anon_read and not row.auth_read


def test_duplicate_finalization_and_exact_question_mapping(module6_database) -> None:
    factory, engine, start, _, settings = module6_database
    execution = start()
    item = load_evidence(factory, execution.id)
    with factory() as session:
        service = CallResultService(session, settings=settings, provider=None)
        first = service.finalize_terminal_evidence(item)
        second = service.finalize_terminal_evidence(item)
    assert first.id == second.id and first.answers[0].outreach_question_id
    with engine.connect() as connection:
        assert connection.execute(text("select count(*) from voice_call_results")).scalar_one() == 1
        answer_count = connection.execute(
            text("select count(*) from voice_screening_answers")
        ).scalar_one()
        assert answer_count == 1


def test_machine_completion_has_no_answers(module6_database) -> None:
    factory, engine, start, _, settings = module6_database
    execution = start()
    item = load_evidence(factory, execution.id, answered_by="MACHINE")
    with factory() as session:
        result = CallResultService(
            session, settings=settings, provider=None
        ).finalize_terminal_evidence(item)
    assert result.screening_result_state == "unavailable"
    with engine.connect() as connection:
        answer_count = connection.execute(
            text("select count(*) from voice_screening_answers")
        ).scalar_one()
        assert answer_count == 0


def test_module6_unknown_remains_unknown_after_terminal_proof(module6_database) -> None:
    factory, engine, start, _, settings = module6_database
    execution = start()
    call_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "update voice_call_executions set status='unknown', provider_call_id=:call_id "
                "where id=:execution_id"
            ),
            {"call_id": call_id, "execution_id": execution.id},
        )
    item = load_evidence(factory, execution.id, call_id=call_id)
    with factory() as session:
        service = CallResultService(session, settings=settings, provider=None)
        service.finalize_terminal_evidence(item)
    with engine.connect() as connection:
        status = connection.execute(
            text("select status from voice_call_executions where id=:id"),
            {"id": execution.id},
        ).scalar_one()
    assert status == "unknown"


def test_concurrent_duplicate_evidence_converges(module6_database) -> None:
    factory, engine, start, _, settings = module6_database
    execution = start()
    item = load_evidence(factory, execution.id)

    def finalize(_value: int):
        with factory() as session:
            return CallResultService(
                session, settings=settings, provider=None
            ).finalize_terminal_evidence(item)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(finalize, range(2)))
    assert results[0].id == results[1].id
    with engine.connect() as connection:
        assert connection.execute(text("select count(*) from voice_call_results")).scalar_one() == 1


def test_database_guards_terminal_identity_and_answer_immutability(module6_database) -> None:
    factory, engine, start, _, settings = module6_database
    execution = start()
    item = load_evidence(factory, execution.id)
    with factory() as session:
        result = CallResultService(
            session, settings=settings, provider=None
        ).finalize_terminal_evidence(item)
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("update voice_call_results set provider_call_id=:new where id=:id"),
            {"new": uuid4(), "id": result.id},
        )
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("update voice_screening_answers set answer_text='changed'"),
        )
