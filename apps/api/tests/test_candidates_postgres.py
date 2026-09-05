"""PostgreSQL qualification for Module 2 identity, concurrency, and rollback invariants."""

from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from app.candidates.errors import CandidateAlreadyExistsError, CandidateIdentityConflictError
from app.candidates.schemas import CandidateCreateRequest, ExternalCandidateObservation
from app.candidates.service import CandidateService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a migrated local Supabase/Postgres database",
)


def _url() -> str:
    assert TEST_DATABASE_URL
    if TEST_DATABASE_URL.startswith("postgresql+psycopg://"):
        return TEST_DATABASE_URL
    return TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture()
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_engine(_url(), pool_pre_ping=True, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    with engine.begin() as connection:
        connection.execute(
            text(
                "truncate table public.candidate_external_identities, "
                "public.candidates restart identity cascade"
            )
        )
    yield factory
    engine.dispose()


def test_database_enforces_case_insensitive_email_phone_and_provider_identity(
    session_factory,
) -> None:
    with session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.candidates(full_name,email,phone_e164) "
                "values ('First','Sarah@Example.com','+919876543210')"
            )
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.candidates(full_name,email) "
                "values ('Second','sarah@example.com')"
            )
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.execute(
            text(
                "insert into public.candidates(full_name,phone_e164) "
                "values ('Second','+919876543210')"
            )
        )

    with session_factory.begin() as session:
        candidate_id = session.execute(
            text("select id from public.candidates limit 1")
        ).scalar_one()
        session.execute(
            text(
                "insert into public.candidate_external_identities"
                "(candidate_id,provider,external_person_id) "
                "values (:id,'apollo','person-1')"
            ),
            {"id": candidate_id},
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        candidate_id = session.execute(
            text("select id from public.candidates limit 1")
        ).scalar_one()
        session.execute(
            text(
                "insert into public.candidate_external_identities"
                "(candidate_id,provider,external_person_id) "
                "values (:id,'apollo','person-1')"
            ),
            {"id": candidate_id},
        )


def test_candidate_tables_enable_rls_and_revoke_browser_roles(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    with session_factory() as session:
        rows = session.execute(
            text(
                "select c.relname, c.relrowsecurity "
                "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='public' and c.relname in "
                "('candidates','candidate_external_identities') order by c.relname"
            )
        ).all()
        assert {row.relname: row.relrowsecurity for row in rows} == {
            "candidate_external_identities": True,
            "candidates": True,
        }

        privileges = session.execute(
            text(
                "select "
                "has_table_privilege('anon','public.candidates','SELECT') as anon_select, "
                "has_table_privilege('authenticated','public.candidates','SELECT') as auth_select"
            )
        ).one()
        assert privileges.anon_select is False
        assert privileges.auth_select is False


def test_external_identity_rows_are_database_immutable(session_factory) -> None:
    with session_factory() as session:
        service = CandidateService(session)
        candidate = service.resolve_external_candidate(
            ExternalCandidateObservation(
                provider="apollo",
                external_person_id="person-immutable",
                full_name="Sarah Ahmed",
            )
        )

    with pytest.raises(DBAPIError), session_factory.begin() as session:
        session.execute(
            text(
                "update public.candidate_external_identities "
                "set external_person_id='changed' where candidate_id=:candidate_id"
            ),
            {"candidate_id": candidate.id},
        )

    with pytest.raises(DBAPIError), session_factory.begin() as session:
        session.execute(
            text(
                "delete from public.candidate_external_identities "
                "where candidate_id=:candidate_id"
            ),
            {"candidate_id": candidate.id},
        )


def test_concurrent_manual_same_email_creates_one_candidate(
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def create() -> None:
        with session_factory() as session:
            service = CandidateService(session)
            barrier.wait()
            try:
                service.create_manual_candidate(
                    CandidateCreateRequest(full_name="Sarah Ahmed", email="sarah@example.com")
                )
                outcomes.append("created")
            except CandidateAlreadyExistsError:
                outcomes.append("existing")

    first = threading.Thread(target=create)
    second = threading.Thread(target=create)
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(outcomes) == ["created", "existing"]
    with session_factory() as session:
        assert session.execute(text("select count(*) from public.candidates")).scalar_one() == 1


def test_concurrent_external_identity_resolution_converges_to_one_candidate(
    session_factory,
) -> None:
    candidate_ids: list[str] = []
    barrier = threading.Barrier(2)
    observation = ExternalCandidateObservation(
        provider="apollo",
        external_person_id="apollo-person-1",
        full_name="Sarah Ahmed",
    )

    def resolve() -> None:
        with session_factory() as session:
            service = CandidateService(session)
            barrier.wait()
            candidate_ids.append(str(service.resolve_external_candidate(observation).id))

    first = threading.Thread(target=resolve)
    second = threading.Thread(target=resolve)
    first.start()
    second.start()
    first.join()
    second.join()

    assert len(set(candidate_ids)) == 1
    with session_factory() as session:
        assert session.execute(text("select count(*) from public.candidates")).scalar_one() == 1
        assert session.execute(
            text("select count(*) from public.candidate_external_identities")
        ).scalar_one() == 1


def test_concurrent_distinct_provider_identities_same_email_fully_converge(
    session_factory,
) -> None:
    candidate_ids: list[str] = []
    barrier = threading.Barrier(2)
    observations = (
        ExternalCandidateObservation(
            provider="apollo",
            external_person_id="apollo-person-1",
            full_name="Sarah Ahmed",
            email="sarah@example.com",
        ),
        ExternalCandidateObservation(
            provider="pdl",
            external_person_id="pdl-person-1",
            full_name="Sarah Ahmed",
            email="sarah@example.com",
        ),
    )

    def resolve(observation: ExternalCandidateObservation) -> None:
        with session_factory() as session:
            service = CandidateService(session)
            barrier.wait()
            candidate_ids.append(str(service.resolve_external_candidate(observation).id))

    threads = [
        threading.Thread(target=resolve, args=(observation,))
        for observation in observations
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(candidate_ids)) == 1
    with session_factory() as session:
        assert session.execute(text("select count(*) from public.candidates")).scalar_one() == 1
        identities = session.execute(
            text(
                "select provider, external_person_id "
                "from public.candidate_external_identities order by provider"
            )
        ).all()
        assert [(row.provider, row.external_person_id) for row in identities] == [
            ("apollo", "apollo-person-1"),
            ("pdl", "pdl-person-1"),
        ]


def test_conflicting_external_identity_rolls_back_without_partial_mutation(
    session_factory,
) -> None:
    with session_factory() as session:
        service = CandidateService(session)
        first = service.create_manual_candidate(
            CandidateCreateRequest(full_name="First", email="first@example.com")
        )
        second = service.create_manual_candidate(
            CandidateCreateRequest(full_name="Second", email="second@example.com")
        )
        linked = service.resolve_external_candidate(
            ExternalCandidateObservation(
                provider="apollo",
                external_person_id="person-a",
                full_name="First",
                email="first@example.com",
            )
        )
        assert linked.id == first.id

    with session_factory() as session:
        service = CandidateService(session)
        with pytest.raises(CandidateIdentityConflictError):
            service.resolve_external_candidate(
                ExternalCandidateObservation(
                    provider="apollo",
                    external_person_id="person-a",
                    full_name="Second",
                    email="second@example.com",
                )
            )

    with session_factory() as session:
        identity = session.execute(
            text(
                "select candidate_id from public.candidate_external_identities "
                "where provider='apollo' and external_person_id='person-a'"
            )
        ).one()
        assert identity.candidate_id == first.id
        second_revision = session.execute(
            text("select revision from public.candidates where id=:id"),
            {"id": second.id},
        ).scalar_one()
        assert second_revision == 0
