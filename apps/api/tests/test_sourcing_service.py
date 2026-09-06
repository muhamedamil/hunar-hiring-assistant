"""Module 3 service tests for approved-version binding, bounded search, and enrichment dedupe."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.jobs.schemas import ApprovedJobDefinition
from app.sourcing.errors import (
    SearchRetryNotAllowedError,
    SourcingProviderError,
    SourcingProviderNotConfiguredError,
)
from app.sourcing.models import SourcingEnrichment, SourcingResult, SourcingRun
from app.sourcing.schemas import (
    EnrichmentPriority,
    ProviderSearchHit,
    ProviderSearchPage,
    ProviderSearchQuery,
    SourcingRunStatus,
    SourcingSearchCriteria,
)
from app.sourcing.service import SourcingService


class FakeSession:
    """Minimal transaction facade used by deterministic Module 3 service tests."""

    def begin(self):  # type: ignore[no-untyped-def]
        return nullcontext()

    def flush(self) -> None:
        """Match the SQLAlchemy flush interface used by services."""


class FakeRepository:
    """In-memory sourcing repository preserving run/result/enrichment state."""

    def __init__(self) -> None:
        self.runs: dict[UUID, SourcingRun] = {}
        self.results: dict[UUID, SourcingResult] = {}
        self.enrichments: dict[UUID, SourcingEnrichment] = {}

    def create_run(self, session: Any, run: SourcingRun) -> SourcingRun:
        del session
        run.id = uuid4()
        now = datetime.now(UTC)
        run.created_at = now
        run.updated_at = now
        self.runs[run.id] = run
        return run

    def get_run(self, session: Any, run_id: UUID) -> SourcingRun | None:
        del session
        return self.runs.get(run_id)

    def get_run_for_update(self, session: Any, run_id: UUID) -> SourcingRun | None:
        del session
        return self.runs.get(run_id)

    def list_runs_for_job(self, session: Any, job_id: UUID) -> list[SourcingRun]:
        del session
        return [run for run in self.runs.values() if run.job_id == job_id]

    def insert_results(
        self,
        session: Any,
        results: list[SourcingResult],
    ) -> list[SourcingResult]:
        del session
        for result in results:
            result.id = uuid4()
            now = datetime.now(UTC)
            result.created_at = now
            result.updated_at = now
            self.results[result.id] = result
        return results

    def list_results(self, session: Any, run_id: UUID) -> list[SourcingResult]:
        del session
        return sorted(
            [item for item in self.results.values() if item.sourcing_run_id == run_id],
            key=lambda item: item.result_position,
        )

    def get_result(self, session: Any, result_id: UUID) -> SourcingResult | None:
        del session
        return self.results.get(result_id)

    def get_result_for_update(self, session: Any, result_id: UUID) -> SourcingResult | None:
        del session
        return self.results.get(result_id)

    def create_enrichment(
        self,
        session: Any,
        enrichment: SourcingEnrichment,
    ) -> SourcingEnrichment:
        del session
        enrichment.id = uuid4()
        now = datetime.now(UTC)
        enrichment.created_at = now
        enrichment.updated_at = now
        self.enrichments[enrichment.id] = enrichment
        return enrichment

    def get_enrichment_by_result(
        self,
        session: Any,
        result_id: UUID,
    ) -> SourcingEnrichment | None:
        del session
        return next(
            (
                item
                for item in self.enrichments.values()
                if item.sourcing_result_id == result_id
            ),
            None,
        )

    def get_enrichment(self, session: Any, enrichment_id: UUID):  # type: ignore[no-untyped-def]
        del session
        return self.enrichments.get(enrichment_id)

    def list_enrichments_for_run(
        self,
        session: Any,
        run_id: UUID,
    ) -> list[SourcingEnrichment]:
        del session
        result_ids = {
            result.id for result in self.results.values() if result.sourcing_run_id == run_id
        }
        return [
            item for item in self.enrichments.values() if item.sourcing_result_id in result_ids
        ]

    def get_evidence_source_for_result(
        self,
        session: Any,
        result_id: UUID,
    ) -> tuple[SourcingEnrichment, SourcingResult, SourcingRun] | None:
        del session
        result = self.results.get(result_id)
        if result is None:
            return None
        enrichment = self.get_enrichment_by_result(None, result_id)
        run = self.runs.get(result.sourcing_run_id)
        if enrichment is None or run is None:
            return None
        return enrichment, result, run


class FakeJobService:
    """Return one immutable approved definition and record downstream binding calls."""

    definition: ApprovedJobDefinition
    calls = 0

    def __init__(self, session: Any) -> None:
        del session

    def lock_ready_definition_for_downstream_binding(
        self,
        job_id: UUID,
    ) -> ApprovedJobDefinition:
        FakeJobService.calls += 1
        assert job_id == self.definition.job_id
        return self.definition


class FakeSearchProvider:
    """Return configured pages while counting read-only provider calls."""

    def __init__(self, pages: list[ProviderSearchPage]) -> None:
        self.pages = pages
        self.calls = 0

    def search_people(self, query):  # type: ignore[no-untyped-def]
        assert query.include_similar_titles is False
        self.calls += 1
        return self.pages[min(self.calls - 1, len(self.pages) - 1)]


class FakeWorkItems:
    """Capture work-item enqueue commands without introducing a second queue implementation."""

    def __init__(self) -> None:
        self.commands: list[Any] = []

    def enqueue(self, session: Any, command):  # type: ignore[no-untyped-def]
        del session
        self.commands.append(command)
        return command


def definition() -> ApprovedJobDefinition:
    """Build one approved Job definition representative of Task-2 sourcing."""

    return ApprovedJobDefinition(
        id=uuid4(),
        job_id=uuid4(),
        version=3,
        title="Senior Backend Engineer",
        company_name="Hunar.ai",
        description="Build reliable backend services for a production AI hiring platform.",
        requirements={
            "alternate_titles": ["Backend Engineer"],
            "required_skills": ["Python"],
            "locations": ["Bangalore"],
            "seniority": ["senior"],
        },
        screening_questions=[],
        created_at=datetime.now(UTC),
    )


def page(count: int = 2) -> ProviderSearchPage:
    """Return a deterministic contact-free provider result page."""

    return ProviderSearchPage(
        hits=[
            ProviderSearchHit(
                external_person_id=f"person-{index}",
                first_name=f"Person {index}",
            )
            for index in range(count)
        ],
        total_matches=100,
    )


def test_search_binds_to_approved_version_and_keeps_hits_out_of_candidate_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = definition()
    FakeJobService.definition = approved
    FakeJobService.calls = 0
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    provider = FakeSearchProvider([page()])
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=provider,
        repository=repository,
    )

    run = service.start_search(approved.job_id, result_limit=10)

    assert FakeJobService.calls == 1
    assert run.definition_version == 3
    assert run.status is SourcingRunStatus.COMPLETED
    assert run.result_count == 2
    assert run.criteria.unmapped_requirements[0].field == "required_skills"
    assert all(result.candidate_id is None for result in run.results)
    assert provider.calls == 1


def test_priority_uses_historical_run_criteria_after_job_reapproval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved_v3 = definition()
    FakeJobService.definition = approved_v3
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    provider = FakeSearchProvider(
        [
            ProviderSearchPage(
                hits=[
                    ProviderSearchHit(
                        external_person_id="person-1",
                        title="Senior Backend Engineer",
                        phone_availability="available",
                    )
                ]
            )
        ]
    )
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=provider,
        repository=repository,
    )
    original = service.start_search(approved_v3.job_id, result_limit=10)
    FakeJobService.definition = approved_v3.model_copy(
        update={"version": 4, "title": "Account Executive"}
    )

    historical = service.get_run(original.id)

    assert historical.definition_version == 3
    assert historical.results[0].enrichment_priority is EnrichmentPriority.RECOMMENDED
    assert provider.calls == 1


def test_matching_evidence_seam_returns_exact_job_and_source_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = definition()
    FakeJobService.definition = approved
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=FakeSearchProvider([page(1)]),
        repository=repository,
    )
    run = service.start_search(approved.job_id, result_limit=10)
    result = repository.results[run.results[0].id]
    candidate_id = uuid4()
    result.candidate_id = candidate_id
    enrichment = SourcingEnrichment(
        sourcing_result_id=result.id,
        provider="apollo",
        status="awaiting_phone",
        candidate_id=candidate_id,
        professional_evidence={
            "current_title": "Backend Engineer",
            "current_organization_name": "Acme",
            "location": None,
            "profile_url": None,
            "employment_history": [],
        },
        evidence_version="professional_evidence_v1",
        updated_at=datetime.now(UTC),
    )
    repository.create_enrichment(None, enrichment)

    source = service.get_matching_evidence_for_sourcing_result(result.id)

    assert source is not None
    assert source.candidate_id == candidate_id
    assert source.sourcing_result_id == result.id
    assert source.sourcing_run_id == run.id
    assert source.job_id == approved.job_id
    assert source.definition_version == 3


def test_service_rejects_over_limit_page_even_if_provider_adapter_is_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = definition()
    FakeJobService.definition = approved
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    provider = FakeSearchProvider([page(11)])
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=provider,
        repository=repository,
    )

    with pytest.raises(SourcingProviderError) as exc_info:
        service.start_search(approved.job_id, result_limit=10)

    assert exc_info.value.code == "APOLLO_SEARCH_RESULT_LIMIT_EXCEEDED"
    run = next(iter(repository.runs.values()))
    assert run.status == "failed"
    assert run.result_count == 0
    assert repository.results == {}


def test_enrichment_double_submit_creates_one_operation_and_one_work_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = definition()
    FakeJobService.definition = approved
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    work_items = FakeWorkItems()
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=FakeSearchProvider([page(1)]),
        repository=repository,
        work_items=work_items,  # type: ignore[arg-type]
    )
    run = service.start_search(approved.job_id, result_limit=10)
    result_id = run.results[0].id

    first = service.request_enrichment(result_id)
    second = service.request_enrichment(result_id)

    assert second.id == first.id
    assert len(repository.enrichments) == 1
    assert len(work_items.commands) == 1
    assert work_items.commands[0].work_type == "apollo_people_enrichment"


def test_enrichment_is_rejected_before_queueing_when_callback_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = definition()
    FakeJobService.definition = approved
    monkeypatch.setattr("app.sourcing.service.JobService", FakeJobService)
    repository = FakeRepository()
    work_items = FakeWorkItems()
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=FakeSearchProvider([page(1)]),
        repository=repository,
        work_items=work_items,  # type: ignore[arg-type]
        enrichment_configured=False,
    )
    run = service.start_search(approved.job_id, result_limit=10)

    with pytest.raises(SourcingProviderNotConfiguredError):
        service.request_enrichment(run.results[0].id)

    assert repository.enrichments == {}
    assert work_items.commands == []


def _searching_run(repository: FakeRepository, *, stale: bool) -> SourcingRun:
    """Create one persisted SEARCHING run suitable for stale-retry tests."""

    query = ProviderSearchQuery(person_titles=["Backend Engineer"], per_page=10)
    criteria = SourcingSearchCriteria(titles=["Backend Engineer"], result_limit=10)
    started_at = datetime.now(UTC) - (timedelta(minutes=10) if stale else timedelta())
    run = SourcingRun(
        job_id=uuid4(),
        definition_version=1,
        provider="apollo",
        status=SourcingRunStatus.SEARCHING.value,
        criteria=criteria.model_dump(mode="json"),
        provider_query=query.model_dump(mode="json"),
        mapping_version="test",
        result_limit=10,
        result_count=0,
        attempt_count=1,
        search_generation=1,
        started_at=started_at,
        updated_at=started_at,
    )
    repository.create_run(None, run)
    run.started_at = started_at
    return run


def test_stale_search_retry_advances_generation_and_reuses_persisted_query() -> None:
    repository = FakeRepository()
    run = _searching_run(repository, stale=True)
    provider = FakeSearchProvider([page(1)])
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=provider,
        repository=repository,
        search_stale_seconds=300,
    )

    retried = service.retry_search(run.id)

    assert retried.status is SourcingRunStatus.COMPLETED
    assert run.search_generation == 2
    assert run.attempt_count == 2
    assert provider.calls == 1


def test_fresh_searching_run_cannot_be_retried() -> None:
    repository = FakeRepository()
    run = _searching_run(repository, stale=False)
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=FakeSearchProvider([page(1)]),
        repository=repository,
        search_stale_seconds=300,
    )

    with pytest.raises(SearchRetryNotAllowedError):
        service.retry_search(run.id)

    assert run.search_generation == 1
    assert run.status == SourcingRunStatus.SEARCHING.value


def test_superseded_search_generation_cannot_overwrite_newer_run_state() -> None:
    repository = FakeRepository()
    run = _searching_run(repository, stale=True)
    run.search_generation = 2
    service = SourcingService(
        FakeSession(),  # type: ignore[arg-type]
        search_provider=FakeSearchProvider([page(1)]),
        repository=repository,
    )

    failed = service._fail_run(  # noqa: SLF001
        run.id,
        search_generation=1,
        code="OLD_EXECUTION_FAILURE",
    )
    completed = service._complete_run(  # noqa: SLF001
        run.id,
        page(1),
        search_generation=1,
    )

    assert failed is False
    assert completed is False
    assert run.status == SourcingRunStatus.SEARCHING.value
    assert run.failure_code is None
    assert repository.results == {}
