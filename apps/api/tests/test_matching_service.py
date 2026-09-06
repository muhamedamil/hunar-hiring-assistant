"""Service tests for shared Task-1/Task-2 Candidate matching and recruiter decisions."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.candidates.schemas import CandidateMatchingSnapshot, CandidateSummaryResponse
from app.core.retry import ProviderError
from app.jobs.errors import JobNotReadyError
from app.jobs.schemas import ApprovedJobDefinition, JobStatus
from app.matching.models import JobCandidate, JobCandidateMatch
from app.matching.schemas import (
    MatchCriterionStatus,
    SemanticCriterionVerdict,
    SemanticMatchOutput,
    ShortlistStatus,
)
from app.matching.service import MatchingService
from app.sourcing.schemas import (
    CandidateProfessionalEvidence,
    ProfessionalExperienceEvidence,
    ResolvedSourcingCandidateEvidenceSource,
)


class FakeSession:
    """Minimal transaction interface for deterministic service tests."""

    def begin(self):
        return nullcontext()

    def flush(self) -> None:
        """Match SQLAlchemy's flush surface used by Module 4 services."""

    def rollback(self) -> None:
        """Match SQLAlchemy rollback used only by bounded uniqueness recovery."""


class FakeMatchingRepository:
    """In-memory Module 4 persistence preserving relation and match identities."""

    def __init__(self) -> None:
        self.relations: dict[UUID, JobCandidate] = {}
        self.matches: dict[UUID, JobCandidateMatch] = {}

    def create_job_candidate(self, session: Any, relation: JobCandidate) -> JobCandidate:
        del session
        now = datetime.now(UTC)
        relation.id = uuid4()
        relation.created_at = now
        relation.updated_at = now
        self.relations[relation.id] = relation
        return relation

    def get_job_candidate(self, session: Any, relation_id: UUID) -> JobCandidate | None:
        del session
        return self.relations.get(relation_id)

    def get_job_candidate_for_update(self, session: Any, relation_id: UUID):
        del session
        return self.relations.get(relation_id)

    def find_job_candidate(self, session: Any, *, job_id: UUID, candidate_id: UUID):
        del session
        return next(
            (
                relation
                for relation in self.relations.values()
                if relation.job_id == job_id and relation.candidate_id == candidate_id
            ),
            None,
        )

    def find_job_candidate_for_update(
        self,
        session: Any,
        *,
        job_id: UUID,
        candidate_id: UUID,
    ):
        return self.find_job_candidate(
            session,
            job_id=job_id,
            candidate_id=candidate_id,
        )

    def list_for_job(self, session: Any, *, job_id: UUID, shortlist_status, limit, offset):
        del session, limit, offset
        return [
            relation
            for relation in self.relations.values()
            if relation.job_id == job_id
            and (shortlist_status is None or relation.shortlist_status == shortlist_status.value)
        ]

    def insert_match(self, session: Any, match: JobCandidateMatch) -> JobCandidateMatch:
        del session
        now = datetime.now(UTC)
        match.id = uuid4()
        match.created_at = now
        if not getattr(match, "started_at", None):
            match.started_at = now
        match.updated_at = getattr(match, "updated_at", now)
        self.matches[match.id] = match
        return match

    def get_match(self, session: Any, match_id: UUID):
        del session
        return self.matches.get(match_id)

    def get_match_for_update(self, session: Any, match_id: UUID):
        del session
        return self.matches.get(match_id)

    def find_active_analysis(self, session: Any, *, relation_id: UUID, analysis_key_hash: str):
        del session
        return next(
            (
                match
                for match in self.matches.values()
                if match.job_candidate_id == relation_id
                and match.analysis_key_hash == analysis_key_hash
                and match.status == "analyzing"
            ),
            None,
        )

    def find_cached_completed(
        self,
        session: Any,
        *,
        relation_id: UUID,
        analysis_key_hash: str,
        require_hybrid: bool,
    ):
        del session
        candidates = [
            match
            for match in self.matches.values()
            if match.job_candidate_id == relation_id
            and match.analysis_key_hash == analysis_key_hash
            and match.status == "completed"
            and (not require_hybrid or match.analysis_mode == "hybrid_gemini")
        ]
        return candidates[-1] if candidates else None

    def list_matches(self, session: Any, *, relation_id: UUID, limit: int, offset: int):
        del session
        values = [m for m in self.matches.values() if m.job_candidate_id == relation_id]
        return list(reversed(values))[offset : offset + limit]

    def list_matches_by_ids(self, session: Any, match_ids: set[UUID]):
        del session
        return {
            match_id: self.matches[match_id]
            for match_id in match_ids
            if match_id in self.matches
        }

    def mark_stale_analysis_failed(self, session: Any, match: JobCandidateMatch, *, completed_at):
        del session
        match.status = "failed"
        match.completed_at = completed_at


class FakeJobService:
    """Expose one mutable current Job and immutable approved definition."""

    definition: ApprovedJobDefinition
    status = JobStatus.READY

    def __init__(self, session: Any) -> None:
        del session

    def lock_ready_definition_for_downstream_binding(self, job_id: UUID) -> ApprovedJobDefinition:
        if self.status is not JobStatus.READY:
            raise JobNotReadyError()
        assert job_id == self.definition.job_id
        return self.definition

    def get_job(self, job_id: UUID):
        assert job_id == self.definition.job_id
        return SimpleNamespace(
            status=self.status,
            approved_version=self.definition.version,
        )

    def get_definition_version(self, job_id: UUID, version: int) -> ApprovedJobDefinition:
        assert job_id == self.definition.job_id
        assert version == self.definition.version
        return self.definition


class FakeCandidateService:
    """Expose one canonical Candidate snapshot and PII-minimized summary."""

    snapshot: CandidateMatchingSnapshot
    summary: CandidateSummaryResponse

    def __init__(self, session: Any) -> None:
        del session

    def lock_matching_snapshot_for_downstream_binding(self, candidate_id: UUID):
        assert candidate_id == self.snapshot.candidate_id
        return self.snapshot

    def get_summaries_by_ids(self, candidate_ids: set[UUID]):
        assert self.summary.id in candidate_ids
        return {self.summary.id: self.summary}


class FakeSourcingService:
    """Expose optional resolved Module 3 provenance for Task-2 convergence tests."""

    sources: dict[UUID, ResolvedSourcingCandidateEvidenceSource] = {}

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def get_resolved_candidate_evidence_source(self, result_id: UUID):
        return self.sources.get(result_id)


class FakeSemanticProvider:
    """Return evidence-citing semantic role support without producing a score."""

    model_name = "gemini-test"

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, *, snapshot, evidence):
        del snapshot
        self.calls += 1
        return SemanticMatchOutput(
            role_alignment=SemanticCriterionVerdict(
                status="supported",
                evidence_ids=[evidence[0].id],
                reason="Explicit title evidence supports role alignment.",
            ),
            seniority_alignment=SemanticCriterionVerdict(
                status="unknown",
                evidence_ids=[],
                reason="Seniority is not established by the supplied titles.",
            ),
        )


class FailingSemanticProvider(FakeSemanticProvider):
    """Fail once per call so fallback and lack of hidden retries are observable."""

    def analyze(self, *, snapshot, evidence):
        del snapshot, evidence
        self.calls += 1
        raise ProviderError(code="GEMINI_TEST_FAILURE", message="provider unavailable")


def configure(monkeypatch):
    job_id = uuid4()
    candidate_id = uuid4()
    FakeJobService.definition = ApprovedJobDefinition(
        id=uuid4(),
        job_id=job_id,
        version=2,
        title="Senior Backend Engineer",
        company_name="Hunar",
        description="Build reliable backend services for the hiring assistant platform.",
        requirements={
            "alternate_titles": ["Backend Engineer"],
            "required_skills": ["Python"],
            "locations": ["Bangalore"],
            "seniority": ["senior"],
        },
        screening_questions=[],
        created_at=datetime.now(UTC),
    )
    FakeJobService.status = JobStatus.READY
    FakeCandidateService.snapshot = CandidateMatchingSnapshot(
        candidate_id=candidate_id,
        candidate_revision=4,
        current_title="Platform Engineer",
        location="Bangalore",
        has_phone=True,
    )
    FakeCandidateService.summary = CandidateSummaryResponse(
        id=candidate_id,
        full_name="Candidate Example",
        current_title="Platform Engineer",
        current_company="Example Co",
        location="Bangalore",
        has_email=True,
        has_phone=True,
        revision=4,
        updated_at=datetime.now(UTC),
    )
    FakeSourcingService.sources = {}
    monkeypatch.setattr("app.matching.service.JobService", FakeJobService)
    monkeypatch.setattr("app.matching.service.CandidateService", FakeCandidateService)
    monkeypatch.setattr("app.matching.service.SourcingService", FakeSourcingService)
    return job_id, candidate_id


def resolved_source(
    *,
    result_id: UUID,
    job_id: UUID,
    candidate_id: UUID,
) -> ResolvedSourcingCandidateEvidenceSource:
    return ResolvedSourcingCandidateEvidenceSource(
        candidate_id=candidate_id,
        sourcing_result_id=result_id,
        sourcing_run_id=uuid4(),
        job_id=job_id,
        definition_version=1,
        professional_evidence=CandidateProfessionalEvidence(
            current_title="Platform Engineer",
            location="Bangalore",
            employment_history=[
                ProfessionalExperienceEvidence(title="Backend Developer", is_current=False)
            ],
        ),
        evidence_version="apollo_professional_evidence_v1",
    )


def test_new_manual_attachment_evaluates_once_and_repeat_returns_existing_truth(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FakeSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )

    first = service.add_manual_candidate(job_id, candidate_id)
    repeated = service.add_manual_candidate(job_id, candidate_id)

    assert first.id == repeated.id
    assert first.current_match is not None
    assert repeated.current_match is not None
    assert repeated.current_match.id == first.current_match.id
    assert len(repository.relations) == 1
    assert len(repository.matches) == 1
    assert provider.calls == 1


def test_new_sourced_context_evaluates_and_same_source_repeat_does_not_rematch(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FakeSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = resolved_source(
        result_id=result_id,
        job_id=job_id,
        candidate_id=candidate_id,
    )

    first = service.add_sourced_candidate(result_id)
    repeated = service.add_sourced_candidate(result_id)

    assert first.id == repeated.id
    assert first.current_match is not None
    assert first.current_match.source_sourcing_result_id == result_id
    assert repeated.current_match is not None
    assert repeated.current_match.id == first.current_match.id
    assert len(repository.matches) == 1
    assert provider.calls == 1


def test_manual_first_new_preferred_source_rematches_but_sourced_first_manual_does_not(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = resolved_source(
        result_id=result_id,
        job_id=job_id,
        candidate_id=candidate_id,
    )

    manual_repository = FakeMatchingRepository()
    manual_provider = FakeSemanticProvider()
    manual_service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=manual_repository,
        semantic_provider=manual_provider,
    )
    manual = manual_service.add_manual_candidate(job_id, candidate_id)
    sourced = manual_service.add_sourced_candidate(result_id)

    assert manual.id == sourced.id
    assert sourced.preferred_sourcing_result_id == result_id
    assert sourced.current_match is not None
    assert sourced.current_match.source_sourcing_result_id == result_id
    assert len(manual_repository.matches) == 2
    assert manual_provider.calls == 2

    sourced_repository = FakeMatchingRepository()
    sourced_provider = FakeSemanticProvider()
    sourced_service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=sourced_repository,
        semantic_provider=sourced_provider,
    )
    sourced_first = sourced_service.add_sourced_candidate(result_id)
    manual_second = sourced_service.add_manual_candidate(job_id, candidate_id)

    assert sourced_first.id == manual_second.id
    assert manual_second.current_match is not None
    assert manual_second.current_match.id == sourced_first.current_match.id  # type: ignore[union-attr]
    assert len(sourced_repository.matches) == 1
    assert sourced_provider.calls == 1


def test_repeated_manual_add_does_not_refresh_a_stale_match(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FakeSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    first = service.add_manual_candidate(job_id, candidate_id)
    FakeCandidateService.snapshot = FakeCandidateService.snapshot.model_copy(
        update={"candidate_revision": 5, "current_title": "Product Manager"}
    )
    FakeCandidateService.summary = FakeCandidateService.summary.model_copy(
        update={"revision": 5, "current_title": "Product Manager"}
    )

    repeated = service.add_manual_candidate(job_id, candidate_id)

    assert repeated.current_match is not None
    assert repeated.current_match.id == first.current_match.id  # type: ignore[union-attr]
    assert repeated.match_freshness.is_fresh is False
    assert provider.calls == 1
    assert len(repository.matches) == 1


def test_repeated_add_and_review_do_not_retry_a_failed_existing_context(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FakeSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = resolved_source(
        result_id=result_id,
        job_id=job_id,
        candidate_id=candidate_id,
    )
    now = datetime.now(UTC)
    relation = repository.create_job_candidate(
        FakeSession(),
        JobCandidate(
            job_id=job_id,
            candidate_id=candidate_id,
            created_source="manual",
            preferred_sourcing_result_id=result_id,
            shortlist_status="reviewing",
            revision=1,
            updated_at=now,
        ),
    )
    repository.insert_match(
        FakeSession(),
        JobCandidateMatch(
            job_candidate_id=relation.id,
            job_id=job_id,
            candidate_id=candidate_id,
            definition_version=2,
            candidate_revision=4,
            input_snapshot={},
            input_hash="f" * 64,
            matcher_version="candidate_job_match_v1",
            analysis_key_hash="e" * 64,
            analysis_mode="hybrid_gemini",
            status="failed",
            semantic_model=provider.model_name,
            started_at=now,
            completed_at=now,
            updated_at=now,
        ),
    )

    manual = service.add_manual_candidate(job_id, candidate_id)
    sourced = service.add_sourced_candidate(result_id)

    assert manual.id == sourced.id == relation.id
    assert manual.current_match is None
    assert sourced.current_match is None
    assert provider.calls == 0
    assert len(repository.matches) == 1


def test_provider_failure_preserves_one_deterministic_fallback_without_hidden_retry(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FailingSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )

    first = service.add_manual_candidate(job_id, candidate_id)
    repeated = service.add_manual_candidate(job_id, candidate_id)

    assert first.current_match is not None
    assert first.current_match.analysis_mode.value == "deterministic_fallback"
    assert first.current_match.semantic_failure_code == "GEMINI_TEST_FAILURE"
    assert repeated.current_match is not None
    assert repeated.current_match.id == first.current_match.id
    assert provider.calls == 1


class TransactionTrackingSession(FakeSession):
    def __init__(self) -> None:
        self.in_transaction = False

    @contextmanager
    def begin(self):
        assert self.in_transaction is False
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False


class TransactionAssertingProvider(FakeSemanticProvider):
    def __init__(self, session: TransactionTrackingSession) -> None:
        super().__init__()
        self.session = session

    def analyze(self, *, snapshot, evidence):
        assert self.session.in_transaction is False
        return super().analyze(snapshot=snapshot, evidence=evidence)


def test_automatic_initial_gemini_call_runs_after_relationship_commit(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    session = TransactionTrackingSession()
    provider = TransactionAssertingProvider(session)
    service = MatchingService(  # type: ignore[arg-type]
        session,
        repository=FakeMatchingRepository(),
        semantic_provider=provider,
    )

    detail = service.add_manual_candidate(job_id, candidate_id)

    assert detail.current_match is not None
    assert provider.calls == 1


def test_manual_and_sourced_paths_converge_to_one_relationship(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]

    manual = service.add_manual_candidate(job_id, candidate_id)
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = ResolvedSourcingCandidateEvidenceSource(
        candidate_id=candidate_id,
        sourcing_result_id=result_id,
        sourcing_run_id=uuid4(),
        job_id=job_id,
        definition_version=1,
        professional_evidence=CandidateProfessionalEvidence(
            current_title="Platform Engineer",
            location="Bangalore",
            employment_history=[
                ProfessionalExperienceEvidence(title="Backend Developer", is_current=False)
            ],
        ),
        evidence_version="apollo_professional_evidence_v1",
    )

    sourced = service.add_sourced_candidate(result_id)

    assert manual.id == sourced.id
    assert len(repository.relations) == 1
    assert sourced.created_source.value == "manual"
    assert sourced.preferred_sourcing_result_id == result_id
    assert manual.current_match is not None
    assert sourced.current_match is not None
    assert sourced.current_match.source_sourcing_result_id == result_id


def test_hybrid_match_uses_semantic_role_evidence_but_keeps_skills_unknown(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = FakeSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    relation = service.add_manual_candidate(job_id, candidate_id)

    match = service.evaluate_match(relation.id)

    reasons = {item.key: item for item in match.match_reasons}
    assert match.analysis_mode.value == "hybrid_gemini"
    assert reasons["role_alignment"].status is MatchCriterionStatus.SUPPORTED
    assert reasons["required_skill_1"].status is MatchCriterionStatus.UNKNOWN
    assert provider.calls == 1

    cached = service.evaluate_match(relation.id)
    assert cached.id == match.id
    assert provider.calls == 1


def test_phone_only_change_does_not_stale_match_or_change_score(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    relation = service.add_manual_candidate(job_id, candidate_id)
    match = service.evaluate_match(relation.id)
    before = service.get_job_candidate(relation.id)

    FakeCandidateService.snapshot = FakeCandidateService.snapshot.model_copy(
        update={"candidate_revision": 5, "has_phone": False}
    )
    FakeCandidateService.summary = FakeCandidateService.summary.model_copy(
        update={"revision": 5, "has_phone": False}
    )
    after = service.get_job_candidate(relation.id)

    assert before.current_match is not None
    assert after.current_match is not None
    assert before.current_match.match_score == match.match_score == after.current_match.match_score
    assert after.match_freshness.is_fresh is True
    assert after.call_readiness.value == "not_ready"


def test_title_change_stales_old_match_and_requires_reanalysis(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    relation = service.add_manual_candidate(job_id, candidate_id)
    service.evaluate_match(relation.id)

    FakeCandidateService.snapshot = FakeCandidateService.snapshot.model_copy(
        update={"candidate_revision": 5, "current_title": "Product Manager"}
    )
    FakeCandidateService.summary = FakeCandidateService.summary.model_copy(
        update={"revision": 5, "current_title": "Product Manager"}
    )

    detail = service.get_job_candidate(relation.id)
    assert detail.match_freshness.is_fresh is False
    assert "candidate_evidence_changed" in detail.match_freshness.stale_reasons


def test_shortlist_decision_is_bound_to_current_match_and_reconfirmable(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    relation = service.add_manual_candidate(job_id, candidate_id)
    service.evaluate_match(relation.id)
    current = service.get_job_candidate(relation.id)

    shortlisted = service.update_shortlist(
        relation.id,
        expected_revision=current.revision,
        status=ShortlistStatus.SHORTLISTED,
    )

    assert shortlisted.shortlist_status is ShortlistStatus.SHORTLISTED
    assert shortlisted.decision_is_current is True


class ReopeningSemanticProvider(FakeSemanticProvider):
    """Reopen the Job while semantic analysis is in flight to exercise late-result safety."""

    def analyze(self, *, snapshot, evidence):
        FakeJobService.status = JobStatus.DRAFT
        return super().analyze(snapshot=snapshot, evidence=evidence)


def test_sourced_candidate_without_professional_evidence_still_enters_module_4(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = ResolvedSourcingCandidateEvidenceSource(
        candidate_id=candidate_id,
        sourcing_result_id=result_id,
        sourcing_run_id=uuid4(),
        job_id=job_id,
        definition_version=1,
        professional_evidence=None,
        evidence_version=None,
    )

    relation = service.add_sourced_candidate(result_id)
    match = service.evaluate_match(relation.id)

    assert relation.created_source.value == "sourcing"
    assert relation.preferred_sourcing_result_id == result_id
    assert match.definition_version == 2
    assert match.source_definition_version == 1


def test_sourcing_v1_evidence_is_provenance_while_match_binds_current_ready_v2(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    result_id = uuid4()
    FakeSourcingService.sources[result_id] = ResolvedSourcingCandidateEvidenceSource(
        candidate_id=candidate_id,
        sourcing_result_id=result_id,
        sourcing_run_id=uuid4(),
        job_id=job_id,
        definition_version=1,
        professional_evidence=CandidateProfessionalEvidence(
            current_title="Platform Engineer",
            location="Bangalore",
            employment_history=[],
        ),
        evidence_version="apollo_professional_evidence_v1",
    )

    relation = service.add_sourced_candidate(result_id)
    match = service.evaluate_match(relation.id)

    assert match.definition_version == 2
    assert match.source_definition_version == 1
    assert match.source_sourcing_result_id == result_id


def test_job_reopen_while_gemini_is_in_flight_keeps_result_historical_only(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = ReopeningSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    relation = service.add_manual_candidate(job_id, candidate_id)

    match = next(iter(repository.matches.values()))
    stored = repository.relations[relation.id]

    assert match.status == "completed"
    assert stored.current_match_id is None
    assert provider.calls == 1


def test_professional_evidence_change_has_specific_freshness_reason(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    result_id = uuid4()
    source = ResolvedSourcingCandidateEvidenceSource(
        candidate_id=candidate_id,
        sourcing_result_id=result_id,
        sourcing_run_id=uuid4(),
        job_id=job_id,
        definition_version=1,
        professional_evidence=CandidateProfessionalEvidence(
            current_title="Platform Engineer",
            location="Bangalore",
            employment_history=[],
        ),
        evidence_version="apollo_professional_evidence_v1",
    )
    FakeSourcingService.sources[result_id] = source
    relation = service.add_sourced_candidate(result_id)
    service.evaluate_match(relation.id)

    FakeSourcingService.sources[result_id] = source.model_copy(
        update={
            "professional_evidence": CandidateProfessionalEvidence(
                current_title="Senior Platform Engineer",
                location="Bangalore",
                employment_history=[],
            )
        }
    )

    detail = service.get_job_candidate(relation.id)

    assert detail.match_freshness.is_fresh is False
    assert detail.match_freshness.stale_reasons == ["professional_evidence_changed"]


def test_job_definition_change_does_not_misreport_candidate_evidence_drift(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    relation = service.add_manual_candidate(job_id, candidate_id)
    service.evaluate_match(relation.id)

    FakeJobService.definition = FakeJobService.definition.model_copy(
        update={"id": uuid4(), "version": 3}
    )
    detail = service.get_job_candidate(relation.id)

    assert detail.match_freshness.is_fresh is False
    assert detail.match_freshness.stale_reasons == ["job_definition_changed"]


def test_draft_job_blocks_reverting_shortlist_to_reviewing(monkeypatch) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    service = MatchingService(FakeSession(), repository=repository)  # type: ignore[arg-type]
    relation = service.add_manual_candidate(job_id, candidate_id)
    service.evaluate_match(relation.id)
    current = service.get_job_candidate(relation.id)
    shortlisted = service.update_shortlist(
        relation.id,
        expected_revision=current.revision,
        status=ShortlistStatus.SHORTLISTED,
    )
    FakeJobService.status = JobStatus.DRAFT

    with pytest.raises(JobNotReadyError):
        service.update_shortlist(
            relation.id,
            expected_revision=shortlisted.revision,
            status=ShortlistStatus.REVIEWING,
        )


class MutatingCandidateSemanticProvider(FakeSemanticProvider):
    """Change fit-relevant Candidate truth while semantic analysis is in flight."""

    def analyze(self, *, snapshot, evidence):
        FakeCandidateService.snapshot = FakeCandidateService.snapshot.model_copy(
            update={"candidate_revision": 5, "current_title": "Product Manager"}
        )
        FakeCandidateService.summary = FakeCandidateService.summary.model_copy(
            update={"revision": 5, "current_title": "Product Manager"}
        )
        return super().analyze(snapshot=snapshot, evidence=evidence)


def test_candidate_change_while_gemini_is_in_flight_keeps_result_historical_only(
    monkeypatch,
) -> None:
    job_id, candidate_id = configure(monkeypatch)
    repository = FakeMatchingRepository()
    provider = MutatingCandidateSemanticProvider()
    service = MatchingService(  # type: ignore[arg-type]
        FakeSession(),
        repository=repository,
        semantic_provider=provider,
    )
    relation = service.add_manual_candidate(job_id, candidate_id)

    match = next(iter(repository.matches.values()))
    stored = repository.relations[relation.id]

    assert match.status == "completed"
    assert stored.current_match_id is None
    assert provider.calls == 1
