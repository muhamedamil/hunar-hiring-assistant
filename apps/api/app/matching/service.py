"""Module 4 service for shared Candidate↔Job matching and recruiter shortlist truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.candidates.schemas import CandidateMatchingSnapshot
from app.candidates.service import CandidateService
from app.core.retry import ProviderError, ProviderRateLimitError
from app.jobs.errors import JobNotReadyError
from app.jobs.schemas import ApprovedJobDefinition, JobStatus
from app.jobs.service import JobService
from app.matching.analysis import CandidateMatchProvider
from app.matching.errors import (
    JobCandidateNotFoundError,
    JobCandidateRevisionConflictError,
    MatchAnalysisInProgressError,
    MatchStateConflictError,
)
from app.matching.models import JobCandidate, JobCandidateMatch
from app.matching.repository import MatchingRepository
from app.matching.schemas import (
    CallReadiness,
    DownstreamOutreachShortlist,
    JobCandidateDetailResponse,
    JobCandidateListResponse,
    JobCandidateSource,
    JobCandidateSummaryResponse,
    MatchAnalysisMode,
    MatchCriterion,
    MatchCriterionStatus,
    MatchEvaluationResponse,
    MatchFreshness,
    MatchHistoryResponse,
    MatchInputSnapshot,
    MatchProfessionalEvidence,
    MatchProfessionalExperience,
    MatchStatus,
    ShortlistStatus,
)
from app.matching.scoring import (
    MATCH_POLICY_VERSION,
    SEMANTIC_PROMPT_VERSION,
    build_analysis_key,
    build_deterministic_criteria,
    build_semantic_evidence,
    calculate_score,
    hash_match_input,
    merge_semantic_output,
    semantic_analysis_is_useful,
)
from app.sourcing.schemas import ResolvedSourcingCandidateEvidenceSource
from app.sourcing.service import SourcingService


class MatchingService:
    """Own Candidate↔Job binding, evidence assessment, freshness, and shortlist decisions."""

    def __init__(
        self,
        session: Session,
        *,
        semantic_provider: CandidateMatchProvider | None = None,
        repository: MatchingRepository | None = None,
        analysis_stale_seconds: float = 90.0,
    ) -> None:
        self._session = session
        self._semantic_provider = semantic_provider
        self._repository = repository or MatchingRepository()
        self._analysis_stale_seconds = max(30.0, analysis_stale_seconds)

    def add_manual_candidate(self, job_id: UUID, candidate_id: UUID) -> JobCandidateDetailResponse:
        """Attach a canonical Candidate and evaluate only a newly created relationship."""

        created = False
        try:
            with self._session.begin():
                JobService(self._session).lock_ready_definition_for_downstream_binding(job_id)
                CandidateService(self._session).lock_matching_snapshot_for_downstream_binding(
                    candidate_id
                )
                existing = self._repository.find_job_candidate(
                    self._session,
                    job_id=job_id,
                    candidate_id=candidate_id,
                )
                if existing is None:
                    created = True
                    now = datetime.now(UTC)
                    existing = JobCandidate(
                        job_id=job_id,
                        candidate_id=candidate_id,
                        created_source=JobCandidateSource.MANUAL.value,
                        shortlist_status=ShortlistStatus.REVIEWING.value,
                        revision=0,
                        updated_at=now,
                    )
                    self._repository.create_job_candidate(self._session, existing)
                relation_id = existing.id
        except IntegrityError as exc:
            if self._constraint_name(exc) != "uq_job_candidates_job_candidate":
                raise
            self._session.rollback()
            created = False
            with self._session.begin():
                existing = self._repository.find_job_candidate(
                    self._session,
                    job_id=job_id,
                    candidate_id=candidate_id,
                )
                if existing is None:
                    raise
                relation_id = existing.id
        if created:
            self.evaluate_match(relation_id)
        return self.get_job_candidate(relation_id)

    def add_sourced_candidate(self, result_id: UUID) -> JobCandidateDetailResponse:
        """Select sourced evidence and evaluate only a newly created matching context."""

        matching_context_created = False
        try:
            with self._session.begin():
                source = self._require_resolved_source(result_id)
                JobService(self._session).lock_ready_definition_for_downstream_binding(
                    source.job_id
                )
                CandidateService(self._session).lock_matching_snapshot_for_downstream_binding(
                    source.candidate_id
                )
                relation = self._repository.find_job_candidate_for_update(
                    self._session,
                    job_id=source.job_id,
                    candidate_id=source.candidate_id,
                )
                now = datetime.now(UTC)
                if relation is None:
                    matching_context_created = True
                    relation = JobCandidate(
                        job_id=source.job_id,
                        candidate_id=source.candidate_id,
                        created_source=JobCandidateSource.SOURCING.value,
                        preferred_sourcing_result_id=source.sourcing_result_id,
                        shortlist_status=ShortlistStatus.REVIEWING.value,
                        revision=0,
                        updated_at=now,
                    )
                    self._repository.create_job_candidate(self._session, relation)
                elif relation.preferred_sourcing_result_id != source.sourcing_result_id:
                    matching_context_created = True
                    relation.preferred_sourcing_result_id = source.sourcing_result_id
                    relation.revision += 1
                    relation.updated_at = now
                    self._session.flush()
                relation_id = relation.id
        except IntegrityError as exc:
            if self._constraint_name(exc) != "uq_job_candidates_job_candidate":
                raise
            self._session.rollback()
            matching_context_created = False
            with self._session.begin():
                source = self._require_resolved_source(result_id)
                relation = self._repository.find_job_candidate_for_update(
                    self._session,
                    job_id=source.job_id,
                    candidate_id=source.candidate_id,
                )
                if relation is None:
                    raise
                if relation.preferred_sourcing_result_id != source.sourcing_result_id:
                    matching_context_created = True
                    relation.preferred_sourcing_result_id = source.sourcing_result_id
                    relation.revision += 1
                    relation.updated_at = datetime.now(UTC)
                    self._session.flush()
                relation_id = relation.id
        if matching_context_created:
            self.evaluate_match(relation_id)
        return self.get_job_candidate(relation_id)

    def list_job_candidates(
        self,
        job_id: UUID,
        *,
        shortlist_status: ShortlistStatus | None,
        limit: int,
        offset: int,
    ) -> JobCandidateListResponse:
        """List shared Candidate↔Job relations using evidence-first recruiter review ordering."""

        JobService(self._session).get_job(job_id)
        relations = self._repository.list_for_job(
            self._session,
            job_id=job_id,
            shortlist_status=shortlist_status,
            limit=10000,
            offset=0,
        )
        summaries = self._build_summaries(relations)
        summaries.sort(key=self._review_order_key)
        return JobCandidateListResponse(
            items=summaries[offset : offset + limit],
            limit=limit,
            offset=offset,
        )

    def get_job_candidate(self, relation_id: UUID) -> JobCandidateDetailResponse:
        """Return one relationship with current match, freshness, and decision state."""

        relation = self._repository.get_job_candidate(self._session, relation_id)
        if relation is None:
            raise JobCandidateNotFoundError()
        summary = self._build_summaries([relation])[0]
        job = JobService(self._session).get_job(relation.job_id)
        return JobCandidateDetailResponse(
            **summary.model_dump(),
            current_job_status=job.status.value,
            current_job_definition_version=(
                job.approved_version if job.status is JobStatus.READY else None
            ),
            decision_match_id=relation.decision_match_id,
        )

    def list_match_history(
        self,
        relation_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> MatchHistoryResponse:
        """Return immutable match attempts for audit and historical Job-version review."""

        if self._repository.get_job_candidate(self._session, relation_id) is None:
            raise JobCandidateNotFoundError()
        matches = self._repository.list_matches(
            self._session,
            relation_id=relation_id,
            limit=limit,
            offset=offset,
        )
        return MatchHistoryResponse(
            items=[self._to_match_response(match) for match in matches],
            limit=limit,
            offset=offset,
        )

    def evaluate_match(self, relation_id: UUID) -> MatchEvaluationResponse:
        """Evaluate evidence with bounded Gemini title semantics when they add information."""

        provider = self._semantic_provider
        with self._session.begin():
            relation = self._require_locked_relation(relation_id)
            snapshot, candidate = self._capture_input_locked(relation)
            input_hash = hash_match_input(snapshot)
            deterministic = build_deterministic_criteria(snapshot)
            semantic_useful = semantic_analysis_is_useful(snapshot, deterministic)
            semantic_model = (
                provider.model_name if provider is not None and semantic_useful else None
            )
            analysis_key = build_analysis_key(
                input_hash=input_hash,
                semantic_model=semantic_model,
            )
            cached = self._repository.find_cached_completed(
                self._session,
                relation_id=relation.id,
                analysis_key_hash=analysis_key,
                require_hybrid=provider is not None and semantic_useful,
            )
            if cached is not None:
                self._promote_current_match(relation, cached, now=datetime.now(UTC))
                return self._to_match_response(cached)

            if provider is None or not semantic_useful:
                failure_code = "GEMINI_NOT_CONFIGURED" if semantic_useful else None
                mode = (
                    MatchAnalysisMode.DETERMINISTIC_FALLBACK
                    if semantic_useful
                    else MatchAnalysisMode.DETERMINISTIC
                )
                match = self._create_completed_match(
                    relation=relation,
                    candidate=candidate,
                    snapshot=snapshot,
                    input_hash=input_hash,
                    analysis_key=analysis_key,
                    mode=mode,
                    criteria=deterministic,
                    semantic_model=None,
                    semantic_failure_code=failure_code,
                    retry_after_seconds=None,
                )
                self._promote_current_match(relation, match, now=datetime.now(UTC))
                return self._to_match_response(match)

            active = self._repository.find_active_analysis(
                self._session,
                relation_id=relation.id,
                analysis_key_hash=analysis_key,
            )
            now = datetime.now(UTC)
            if active is not None:
                if active.started_at > now - timedelta(seconds=self._analysis_stale_seconds):
                    raise MatchAnalysisInProgressError()
                self._repository.mark_stale_analysis_failed(
                    self._session,
                    active,
                    completed_at=now,
                )

            match = JobCandidateMatch(
                job_candidate_id=relation.id,
                job_id=relation.job_id,
                candidate_id=relation.candidate_id,
                definition_version=snapshot.definition_version,
                source_sourcing_result_id=snapshot.source_sourcing_result_id,
                source_sourcing_run_id=snapshot.source_sourcing_run_id,
                source_definition_version=snapshot.source_definition_version,
                source_evidence_version=snapshot.source_evidence_version,
                candidate_revision=candidate.candidate_revision,
                input_snapshot=snapshot.model_dump(mode="json"),
                input_hash=input_hash,
                matcher_version=MATCH_POLICY_VERSION,
                analysis_key_hash=analysis_key,
                analysis_mode=MatchAnalysisMode.HYBRID_GEMINI.value,
                status=MatchStatus.ANALYZING.value,
                semantic_model=provider.model_name,
                semantic_prompt_version=SEMANTIC_PROMPT_VERSION,
                started_at=now,
                updated_at=now,
            )
            try:
                self._repository.insert_match(self._session, match)
            except IntegrityError as exc:
                if self._constraint_name(exc) == "uq_candidate_matches_active_analysis":
                    raise MatchAnalysisInProgressError() from exc
                raise
            match_id = match.id
            evidence = build_semantic_evidence(snapshot)

        semantic_output = None
        semantic_failure_code: str | None = None
        retry_after_seconds: int | None = None
        try:
            semantic_output = provider.analyze(snapshot=snapshot, evidence=evidence)
        except ProviderRateLimitError as exc:
            semantic_failure_code = exc.code
            retry_after_seconds = (
                int(exc.retry_after_seconds) if exc.retry_after_seconds is not None else None
            )
        except ProviderError as exc:
            semantic_failure_code = exc.code

        criteria = deterministic
        mode = MatchAnalysisMode.DETERMINISTIC_FALLBACK
        if semantic_output is not None:
            try:
                criteria = merge_semantic_output(
                    deterministic,
                    semantic_output,
                    valid_evidence_ids={item.id for item in evidence},
                )
                mode = MatchAnalysisMode.HYBRID_GEMINI
            except ValueError:
                semantic_failure_code = "GEMINI_CANDIDATE_MATCH_EVIDENCE_INVALID"

        with self._session.begin():
            locked_match = self._repository.get_match_for_update(self._session, match_id)
            if locked_match is None:
                raise RuntimeError("In-flight Candidate match disappeared before finalization")
            if locked_match.status != MatchStatus.ANALYZING.value:
                return self._to_match_response(locked_match)
            relation = self._require_locked_relation(relation_id)
            score = calculate_score(criteria)
            completed_at = datetime.now(UTC)
            locked_match.analysis_mode = mode.value
            locked_match.status = MatchStatus.COMPLETED.value
            locked_match.semantic_failure_code = semantic_failure_code
            locked_match.retry_after_seconds = retry_after_seconds
            locked_match.match_score = score.match_score
            locked_match.evidence_coverage = score.evidence_coverage
            locked_match.match_reasons = [item.model_dump(mode="json") for item in criteria]
            locked_match.completed_at = completed_at
            locked_match.updated_at = completed_at
            self._session.flush()

            try:
                current_snapshot, _ = self._capture_input_locked(relation)
            except JobNotReadyError:
                current_snapshot = None
            if current_snapshot is not None:
                current_hash = hash_match_input(current_snapshot)
                if (
                    current_hash == locked_match.input_hash
                    and current_snapshot.definition_version == locked_match.definition_version
                ):
                    self._promote_current_match(relation, locked_match, now=completed_at)
            return self._to_match_response(locked_match)

    def update_shortlist(
        self,
        relation_id: UUID,
        *,
        expected_revision: int,
        status: ShortlistStatus,
    ) -> JobCandidateDetailResponse:
        """Apply one explicit recruiter decision against the exact current match truth."""

        with self._session.begin():
            relation = self._require_locked_relation(relation_id)
            if relation.revision != expected_revision:
                raise JobCandidateRevisionConflictError(current_revision=relation.revision)
            JobService(self._session).lock_ready_definition_for_downstream_binding(
                relation.job_id
            )

            if status is ShortlistStatus.REVIEWING:
                if (
                    relation.shortlist_status != ShortlistStatus.REVIEWING.value
                    or relation.decision_match_id is not None
                ):
                    relation.shortlist_status = ShortlistStatus.REVIEWING.value
                    relation.decision_match_id = None
                    relation.revision += 1
                    relation.updated_at = datetime.now(UTC)
                    self._session.flush()
                return_id = relation.id
            else:
                if relation.current_match_id is None:
                    raise MatchStateConflictError(
                        code="CURRENT_MATCH_REQUIRED",
                        message="Analyze the current Candidate evidence before making a decision.",
                    )
                match = self._repository.get_match(self._session, relation.current_match_id)
                if match is None or match.status != MatchStatus.COMPLETED.value:
                    raise MatchStateConflictError(
                        code="CURRENT_MATCH_REQUIRED",
                        message="A completed current match is required before this decision.",
                    )
                freshness = self._freshness_locked(relation, match)
                if not freshness.is_fresh:
                    raise MatchStateConflictError(
                        code="CURRENT_MATCH_STALE",
                        message="Refresh the Candidate match before making this decision.",
                    )
                if (
                    relation.shortlist_status != status.value
                    or relation.decision_match_id != match.id
                ):
                    relation.shortlist_status = status.value
                    relation.decision_match_id = match.id
                    relation.revision += 1
                    relation.updated_at = datetime.now(UTC)
                    self._session.flush()
                return_id = relation.id
        return self.get_job_candidate(return_id)

    def lock_current_shortlist_for_downstream_outreach(
        self,
        relation_id: UUID,
    ) -> DownstreamOutreachShortlist:
        """Lock and prove the exact current shortlist authority consumed by Module 5.

        The caller owns the transaction. Lock order is JobCandidate, Job, then Candidate,
        matching the established Module 4 multi-authority mutation order.
        """

        relation = self._require_locked_relation(relation_id)
        if (
            relation.shortlist_status != ShortlistStatus.SHORTLISTED.value
            or relation.current_match_id is None
            or relation.decision_match_id != relation.current_match_id
        ):
            raise MatchStateConflictError(
                code="OUTREACH_SHORTLIST_NOT_CURRENT",
                message="A current shortlisted decision is required before outreach.",
            )

        definition = JobService(self._session).lock_ready_definition_for_downstream_binding(
            relation.job_id
        )
        candidate = CandidateService(
            self._session
        ).lock_matching_snapshot_for_downstream_binding(relation.candidate_id)
        match = self._repository.get_match(self._session, relation.current_match_id)
        if match is None or match.status != MatchStatus.COMPLETED.value:
            raise MatchStateConflictError(
                code="OUTREACH_MATCH_NOT_COMPLETED",
                message="A completed current match is required before outreach.",
            )

        source = self._source_for_relation(relation)
        current = self._build_input(definition, candidate, source)
        if (
            match.definition_version != definition.version
            or hash_match_input(current) != match.input_hash
            or match.matcher_version != MATCH_POLICY_VERSION
        ):
            raise MatchStateConflictError(
                code="OUTREACH_MATCH_STALE",
                message="Refresh and shortlist the current match before outreach.",
            )

        return DownstreamOutreachShortlist(
            job_candidate_id=relation.id,
            job_id=relation.job_id,
            candidate_id=relation.candidate_id,
            decision_match_id=match.id,
            definition_version=match.definition_version,
        )

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        """Return the PostgreSQL constraint name associated with an integrity failure."""

        original = getattr(exc, "orig", None)
        diagnostic = getattr(original, "diag", None)
        value = getattr(diagnostic, "constraint_name", None)
        return str(value) if value else None

    def _require_locked_relation(self, relation_id: UUID) -> JobCandidate:
        relation = self._repository.get_job_candidate_for_update(self._session, relation_id)
        if relation is None:
            raise JobCandidateNotFoundError()
        return relation

    def _require_resolved_source(self, result_id: UUID) -> ResolvedSourcingCandidateEvidenceSource:
        source = SourcingService(
            self._session,
            search_provider=None,
            enrichment_configured=False,
        ).get_resolved_candidate_evidence_source(result_id)
        if source is None:
            raise MatchStateConflictError(
                code="SOURCING_CANDIDATE_NOT_RESOLVED",
                message="Enrich and resolve this sourcing result before reviewing its match.",
            )
        return source

    def _source_for_relation(
        self,
        relation: JobCandidate,
    ) -> ResolvedSourcingCandidateEvidenceSource | None:
        if relation.preferred_sourcing_result_id is None:
            return None
        source = self._require_resolved_source(relation.preferred_sourcing_result_id)
        if source.job_id != relation.job_id or source.candidate_id != relation.candidate_id:
            raise RuntimeError("Preferred sourcing evidence does not belong to this Job Candidate")
        return source

    def _capture_input_locked(
        self,
        relation: JobCandidate,
    ) -> tuple[MatchInputSnapshot, CandidateMatchingSnapshot]:
        definition = JobService(self._session).lock_ready_definition_for_downstream_binding(
            relation.job_id
        )
        candidate = CandidateService(self._session).lock_matching_snapshot_for_downstream_binding(
            relation.candidate_id
        )
        source = self._source_for_relation(relation)
        return self._build_input(definition, candidate, source), candidate

    @staticmethod
    def _build_input(
        definition: ApprovedJobDefinition,
        candidate: CandidateMatchingSnapshot,
        source: ResolvedSourcingCandidateEvidenceSource | None,
    ) -> MatchInputSnapshot:
        professional = None
        if source is not None and source.professional_evidence is not None:
            evidence = source.professional_evidence
            professional = MatchProfessionalEvidence(
                current_title=evidence.current_title,
                location=evidence.location,
                employment_history=[
                    MatchProfessionalExperience(
                        title=item.title,
                        started_at=item.started_at,
                        is_current=item.is_current,
                    )
                    for item in evidence.employment_history
                ],
            )
        requirements = definition.requirements
        return MatchInputSnapshot(
            job_id=definition.job_id,
            definition_version=definition.version,
            job_title=definition.title,
            alternate_titles=requirements.alternate_titles,
            locations=requirements.locations,
            seniority=requirements.seniority,
            required_skills=requirements.required_skills,
            preferred_skills=requirements.preferred_skills,
            min_years_experience=requirements.min_years_experience,
            employment_type=requirements.employment_type,
            work_arrangement=requirements.work_arrangement,
            candidate_id=candidate.candidate_id,
            candidate_current_title=candidate.current_title,
            candidate_location=candidate.location,
            source_sourcing_result_id=(source.sourcing_result_id if source else None),
            source_sourcing_run_id=(source.sourcing_run_id if source else None),
            source_definition_version=(source.definition_version if source else None),
            source_evidence_version=(source.evidence_version if source else None),
            professional_evidence=professional,
        )

    def _create_completed_match(
        self,
        *,
        relation: JobCandidate,
        candidate: CandidateMatchingSnapshot,
        snapshot: MatchInputSnapshot,
        input_hash: str,
        analysis_key: str,
        mode: MatchAnalysisMode,
        criteria: list[MatchCriterion],
        semantic_model: str | None,
        semantic_failure_code: str | None,
        retry_after_seconds: int | None,
    ) -> JobCandidateMatch:
        now = datetime.now(UTC)
        score = calculate_score(criteria)
        match = JobCandidateMatch(
            job_candidate_id=relation.id,
            job_id=relation.job_id,
            candidate_id=relation.candidate_id,
            definition_version=snapshot.definition_version,
            source_sourcing_result_id=snapshot.source_sourcing_result_id,
            source_sourcing_run_id=snapshot.source_sourcing_run_id,
            source_definition_version=snapshot.source_definition_version,
            source_evidence_version=snapshot.source_evidence_version,
            candidate_revision=candidate.candidate_revision,
            input_snapshot=snapshot.model_dump(mode="json"),
            input_hash=input_hash,
            matcher_version=MATCH_POLICY_VERSION,
            analysis_key_hash=analysis_key,
            analysis_mode=mode.value,
            status=MatchStatus.COMPLETED.value,
            semantic_model=semantic_model,
            semantic_prompt_version=(SEMANTIC_PROMPT_VERSION if semantic_model else None),
            semantic_failure_code=semantic_failure_code,
            retry_after_seconds=retry_after_seconds,
            match_score=score.match_score,
            evidence_coverage=score.evidence_coverage,
            match_reasons=[item.model_dump(mode="json") for item in criteria],
            started_at=now,
            completed_at=now,
            updated_at=now,
        )
        return self._repository.insert_match(self._session, match)

    @staticmethod
    def _promote_current_match(
        relation: JobCandidate,
        match: JobCandidateMatch,
        *,
        now: datetime,
    ) -> None:
        if relation.current_match_id != match.id:
            relation.current_match_id = match.id
            relation.revision += 1
            relation.updated_at = now

    def _freshness_locked(
        self,
        relation: JobCandidate,
        match: JobCandidateMatch,
    ) -> MatchFreshness:
        snapshot, _ = self._capture_input_locked(relation)
        reasons: list[str] = []
        if snapshot.definition_version != match.definition_version:
            reasons.append("job_definition_changed")
        if hash_match_input(snapshot) != match.input_hash:
            stored = MatchInputSnapshot.model_validate(match.input_snapshot)
            reasons.extend(self._classify_input_drift(snapshot, stored))
        if match.matcher_version != MATCH_POLICY_VERSION:
            reasons.append("matcher_version_changed")
        return MatchFreshness(is_fresh=not reasons, stale_reasons=list(dict.fromkeys(reasons)))

    def _freshness_read(
        self,
        relation: JobCandidate,
        match: JobCandidateMatch | None,
        *,
        candidate: CandidateMatchingSnapshot,
        job_status: JobStatus,
        definition: ApprovedJobDefinition | None,
    ) -> MatchFreshness:
        if match is None:
            return MatchFreshness(is_fresh=False, stale_reasons=["match_missing"])
        if job_status is not JobStatus.READY or definition is None:
            return MatchFreshness(is_fresh=False, stale_reasons=["job_not_ready"])
        source = self._source_for_relation(relation)
        snapshot = self._build_input(definition, candidate, source)
        reasons: list[str] = []
        if match.definition_version != definition.version:
            reasons.append("job_definition_changed")
        current_hash = hash_match_input(snapshot)
        if current_hash != match.input_hash:
            stored = MatchInputSnapshot.model_validate(match.input_snapshot)
            reasons.extend(self._classify_input_drift(snapshot, stored))
        if match.matcher_version != MATCH_POLICY_VERSION:
            reasons.append("matcher_version_changed")
        return MatchFreshness(is_fresh=not reasons, stale_reasons=reasons)


    @staticmethod
    def _classify_input_drift(
        current: MatchInputSnapshot,
        stored: MatchInputSnapshot,
    ) -> list[str]:
        """Classify non-Job match-input changes without conflating independent authorities."""

        reasons: list[str] = []
        if (
            current.source_sourcing_result_id != stored.source_sourcing_result_id
            or current.source_sourcing_run_id != stored.source_sourcing_run_id
            or current.source_definition_version != stored.source_definition_version
        ):
            reasons.append("professional_source_changed")
        elif (
            current.source_evidence_version != stored.source_evidence_version
            or current.professional_evidence != stored.professional_evidence
        ):
            reasons.append("professional_evidence_changed")
        if (
            current.candidate_current_title != stored.candidate_current_title
            or current.candidate_location != stored.candidate_location
        ):
            reasons.append("candidate_evidence_changed")
        return reasons

    def _build_summaries(
        self,
        relations: list[JobCandidate],
    ) -> list[JobCandidateSummaryResponse]:
        if not relations:
            return []
        candidate_service = CandidateService(self._session)
        candidate_summaries = candidate_service.get_summaries_by_ids(
            {relation.candidate_id for relation in relations}
        )
        match_map = self._repository.list_matches_by_ids(
            self._session,
            {relation.current_match_id for relation in relations if relation.current_match_id},
        )
        jobs: dict[UUID, tuple[JobStatus, ApprovedJobDefinition | None]] = {}
        for job_id in {relation.job_id for relation in relations}:
            job = JobService(self._session).get_job(job_id)
            definition = (
                JobService(self._session).get_definition_version(job_id, job.approved_version)
                if job.status is JobStatus.READY and job.approved_version is not None
                else None
            )
            jobs[job_id] = (job.status, definition)

        items: list[JobCandidateSummaryResponse] = []
        for relation in relations:
            summary = candidate_summaries[relation.candidate_id]
            candidate = CandidateMatchingSnapshot(
                candidate_id=summary.id,
                candidate_revision=summary.revision,
                current_title=summary.current_title,
                location=summary.location,
                has_phone=summary.has_phone,
            )
            match = match_map.get(relation.current_match_id) if relation.current_match_id else None
            job_status, definition = jobs[relation.job_id]
            freshness = self._freshness_read(
                relation,
                match,
                candidate=candidate,
                job_status=job_status,
                definition=definition,
            )
            current_match = self._to_match_response(match) if match is not None else None
            items.append(
                JobCandidateSummaryResponse(
                    id=relation.id,
                    job_id=relation.job_id,
                    candidate=summary,
                    created_source=JobCandidateSource(relation.created_source),
                    preferred_sourcing_result_id=relation.preferred_sourcing_result_id,
                    shortlist_status=ShortlistStatus(relation.shortlist_status),
                    revision=relation.revision,
                    current_match=current_match,
                    match_freshness=freshness,
                    decision_is_current=(
                        freshness.is_fresh
                        and relation.decision_match_id is not None
                        and relation.decision_match_id == relation.current_match_id
                    ),
                    call_readiness=(
                        CallReadiness.READY if summary.has_phone else CallReadiness.NOT_READY
                    ),
                    created_at=relation.created_at,
                    updated_at=relation.updated_at,
                )
            )
        return items

    @staticmethod
    def _review_order_key(item: JobCandidateSummaryResponse) -> tuple[object, ...]:
        match = item.current_match
        role_rank = 3
        if match is not None:
            role = next(
                (reason for reason in match.match_reasons if reason.key == "role_alignment"),
                None,
            )
            if role is not None:
                role_rank = {
                    MatchCriterionStatus.SUPPORTED: 0,
                    MatchCriterionStatus.UNKNOWN: 1,
                    MatchCriterionStatus.CONTRADICTED: 2,
                }[role.status]
        return (
            0 if item.match_freshness.is_fresh else 1,
            role_rank,
            -(match.match_score if match and match.match_score is not None else -1),
            -(match.evidence_coverage if match and match.evidence_coverage is not None else -1),
            0 if item.call_readiness is CallReadiness.READY else 1,
            -item.updated_at.timestamp(),
        )

    @staticmethod
    def _to_match_response(match: JobCandidateMatch) -> MatchEvaluationResponse:
        reasons = [
            MatchCriterion.model_validate(item) for item in (match.match_reasons or [])
        ]
        return MatchEvaluationResponse(
            id=match.id,
            job_candidate_id=match.job_candidate_id,
            definition_version=match.definition_version,
            source_sourcing_result_id=match.source_sourcing_result_id,
            source_sourcing_run_id=match.source_sourcing_run_id,
            source_definition_version=match.source_definition_version,
            source_evidence_version=match.source_evidence_version,
            candidate_revision=match.candidate_revision,
            matcher_version=match.matcher_version,
            analysis_mode=MatchAnalysisMode(match.analysis_mode),
            status=MatchStatus(match.status),
            semantic_model=match.semantic_model,
            semantic_prompt_version=match.semantic_prompt_version,
            semantic_failure_code=match.semantic_failure_code,
            retry_after_seconds=match.retry_after_seconds,
            match_score=match.match_score,
            evidence_coverage=match.evidence_coverage,
            match_reasons=reasons,
            started_at=match.started_at,
            completed_at=match.completed_at,
            created_at=match.created_at,
        )
