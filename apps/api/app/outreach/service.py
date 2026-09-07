"""Module 5 orchestration for immutable outreach preparation and readiness."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.candidates.service import CandidateService
from app.core.errors import AppError
from app.jobs.domain import assert_unique_screening_question_keys
from app.jobs.service import JobService
from app.matching.schemas import DownstreamOutreachShortlist
from app.matching.service import MatchingService
from app.outreach.errors import (
    OutreachNotDispatchableError,
    OutreachNotFoundError,
    OutreachPreparationStaleError,
    OutreachQuestionCountError,
    OutreachQuestionProvenanceError,
    OutreachStateError,
)
from app.outreach.models import OutreachRequest
from app.outreach.repository import OutreachRepository
from app.outreach.schemas import (
    OutreachDispatchSnapshot,
    OutreachPreparationResponse,
    OutreachReadiness,
    OutreachRequestListResponse,
    OutreachRequestResponse,
    OutreachScreeningQuestion,
    OutreachScreeningQuestionDraft,
    drafts_from_job_questions,
)

_EXACT_CONTEXT_CONSTRAINT = "uq_outreach_requests_exact_context"


def canonical_screening_context_hash(questions: list[OutreachScreeningQuestionDraft]) -> str:
    """Hash only ordered normalized screening semantics and exact Job provenance."""

    payload = [question.model_dump(mode="json") for question in questions]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def preparation_state_fingerprint(
    *,
    job_candidate_id: UUID,
    decision_match_id: UUID,
    definition_version: int,
    phone_e164: str | None,
) -> str:
    """Return an unsigned optimistic fingerprint for the authority HR reviewed."""

    payload = {
        "canonical_phone": phone_e164,
        "decision_match_id": str(decision_match_id),
        "definition_version": definition_version,
        "job_candidate_id": str(job_candidate_id),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def mask_phone(phone_e164: str) -> str:
    """Mask canonical phone for browser responses while retaining recognition."""

    prefix = phone_e164[:3]
    hidden = max(2, len(phone_e164) - len(prefix) - 4)
    return f"{prefix}{'•' * hidden}{phone_e164[-4:]}"


class OutreachService:
    """Freeze HR-confirmed outreach context and derive readiness from upstream truth."""

    def __init__(self, session: Session, *, repository: OutreachRepository | None = None) -> None:
        self._session = session
        self._repository = repository or OutreachRepository()

    def get_preparation(self, job_candidate_id: UUID) -> OutreachPreparationResponse:
        """Build a non-persisting preparation view from current locked authorities."""

        with self._session.begin():
            shortlist, phone = self._lock_current_context(job_candidate_id)
            definition = JobService(self._session).get_definition_version(
                shortlist.job_id, shortlist.definition_version
            )
            candidate = CandidateService(self._session).get_summaries_by_ids(
                {shortlist.candidate_id}
            )[shortlist.candidate_id]
            token = preparation_state_fingerprint(
                job_candidate_id=shortlist.job_candidate_id,
                decision_match_id=shortlist.decision_match_id,
                definition_version=shortlist.definition_version,
                phone_e164=phone,
            )
            blockers = [] if phone is not None else ["canonical_phone_missing"]
            return OutreachPreparationResponse(
                job_candidate_id=shortlist.job_candidate_id,
                candidate_id=shortlist.candidate_id,
                candidate_name=candidate.full_name,
                job_id=shortlist.job_id,
                role=definition.title,
                definition_version=shortlist.definition_version,
                masked_phone=mask_phone(phone) if phone is not None else None,
                default_screening_questions=drafts_from_job_questions(
                    definition.screening_questions
                ),
                preparation_token=token,
                can_prepare=not blockers,
                blockers=blockers,
            )

    def prepare_outreach(
        self,
        job_candidate_id: UUID,
        *,
        preparation_token: str,
        screening_questions: list[OutreachScreeningQuestionDraft],
    ) -> OutreachRequestResponse:
        """Idempotently persist the exact immutable outreach context HR confirmed."""

        context_hash = ""
        shortlist: DownstreamOutreachShortlist | None = None
        phone = ""
        try:
            with self._session.begin():
                shortlist, canonical_phone = self._lock_current_context(job_candidate_id)
                if canonical_phone is None:
                    raise OutreachStateError(
                        code="OUTREACH_PHONE_REQUIRED",
                        message="A canonical Candidate phone is required for voice outreach.",
                    )
                phone = canonical_phone
                definition = JobService(self._session).get_definition_version(
                    shortlist.job_id, shortlist.definition_version
                )
                current_token = preparation_state_fingerprint(
                    job_candidate_id=shortlist.job_candidate_id,
                    decision_match_id=shortlist.decision_match_id,
                    definition_version=shortlist.definition_version,
                    phone_e164=phone,
                )
                if preparation_token != current_token:
                    raise OutreachPreparationStaleError()
                if not 1 <= len(screening_questions) <= 10:
                    raise OutreachQuestionCountError()

                normalized = [
                    OutreachScreeningQuestionDraft.model_validate(
                        question.model_dump(mode="python")
                    )
                    for question in screening_questions
                ]
                assert_unique_screening_question_keys(normalized)
                approved_ids = {question.id for question in definition.screening_questions}
                if any(
                    question.source_job_question_id is not None
                    and question.source_job_question_id not in approved_ids
                    for question in normalized
                ):
                    raise OutreachQuestionProvenanceError()

                context_hash = canonical_screening_context_hash(normalized)
                existing = self._repository.find_exact(
                    self._session,
                    job_candidate_id=shortlist.job_candidate_id,
                    decision_match_id=shortlist.decision_match_id,
                    phone_e164_snapshot=phone,
                    screening_context_hash=context_hash,
                )
                if existing is not None:
                    return self._to_response(existing, stale_reasons=[])

                frozen = [
                    OutreachScreeningQuestion(id=uuid4(), **question.model_dump(mode="python"))
                    for question in normalized
                ]
                request = OutreachRequest(
                    job_candidate_id=shortlist.job_candidate_id,
                    decision_match_id=shortlist.decision_match_id,
                    phone_e164_snapshot=phone,
                    screening_questions_snapshot=[
                        question.model_dump(mode="json") for question in frozen
                    ],
                    screening_context_hash=context_hash,
                )
                self._repository.insert(self._session, request)
                return self._to_response(request, stale_reasons=[])
        except IntegrityError as exc:
            if self._constraint_name(exc) != _EXACT_CONTEXT_CONSTRAINT:
                raise
            self._session.rollback()
            if shortlist is None:
                raise
            with self._session.begin():
                existing = self._repository.find_exact(
                    self._session,
                    job_candidate_id=shortlist.job_candidate_id,
                    decision_match_id=shortlist.decision_match_id,
                    phone_e164_snapshot=phone,
                    screening_context_hash=context_hash,
                )
                if existing is None:
                    raise
                return self._to_response(existing, stale_reasons=[])

    def get_outreach_request(self, request_id: UUID) -> OutreachRequestResponse:
        """Return one immutable request with readiness derived from current truth."""

        with self._session.begin():
            request = self._repository.get(self._session, request_id)
            if request is None:
                raise OutreachNotFoundError()
            return self._to_response(request, stale_reasons=self._current_stale_reasons(request))

    def list_outreach_requests(self, *, limit: int, offset: int) -> OutreachRequestListResponse:
        """List immutable requests and derive readiness independently for each row."""

        with self._session.begin():
            request_ids = [
                request.id
                for request in self._repository.list(self._session, limit=limit, offset=offset)
            ]
        return OutreachRequestListResponse(
            items=[self.get_outreach_request(request_id) for request_id in request_ids],
            limit=limit,
            offset=offset,
        )

    def lock_dispatchable_outreach(self, request_id: UUID) -> OutreachDispatchSnapshot:
        """Return the exact frozen snapshot only while all current authorities remain valid.

        The future Module 6 caller owns the surrounding transaction. No work item, provider call,
        or side effect occurs here.
        """

        request = self._repository.get(self._session, request_id)
        if request is None:
            raise OutreachNotFoundError()
        reasons = self._current_stale_reasons(request)
        if reasons:
            raise OutreachNotDispatchableError(reasons=reasons)
        shortlist = MatchingService(self._session).lock_current_shortlist_for_downstream_outreach(
            request.job_candidate_id
        )
        return OutreachDispatchSnapshot(
            outreach_request_id=request.id,
            job_candidate_id=request.job_candidate_id,
            job_id=shortlist.job_id,
            candidate_id=shortlist.candidate_id,
            decision_match_id=request.decision_match_id,
            definition_version=shortlist.definition_version,
            phone_e164=request.phone_e164_snapshot,
            screening_questions=self._parse_questions(request),
        )

    def _lock_current_context(
        self, job_candidate_id: UUID
    ) -> tuple[DownstreamOutreachShortlist, str | None]:
        shortlist = MatchingService(self._session).lock_current_shortlist_for_downstream_outreach(
            job_candidate_id
        )
        contact = CandidateService(self._session).lock_outreach_contact_for_downstream_binding(
            shortlist.candidate_id
        )
        return shortlist, contact.phone_e164

    def _current_stale_reasons(self, request: OutreachRequest) -> list[str]:
        try:
            shortlist, phone = self._lock_current_context(request.job_candidate_id)
        except AppError:
            return ["shortlist_or_match_changed"]
        reasons: list[str] = []
        if shortlist.decision_match_id != request.decision_match_id:
            reasons.append("decision_match_changed")
        if phone != request.phone_e164_snapshot:
            reasons.append("canonical_phone_changed")
        return reasons

    @staticmethod
    def _parse_questions(request: OutreachRequest) -> list[OutreachScreeningQuestion]:
        return [
            OutreachScreeningQuestion.model_validate(question)
            for question in request.screening_questions_snapshot
        ]

    def _candidate_display(self, job_candidate_id: UUID) -> tuple[str, str | None]:
        """Read current non-contact Candidate display fields through Module 4's service seam."""

        relation = MatchingService(self._session).get_job_candidate(job_candidate_id)
        return relation.candidate.full_name, relation.candidate.location

    def _to_response(
        self, request: OutreachRequest, *, stale_reasons: list[str]
    ) -> OutreachRequestResponse:
        candidate_name, candidate_location = self._candidate_display(request.job_candidate_id)
        return OutreachRequestResponse(
            id=request.id,
            job_candidate_id=request.job_candidate_id,
            decision_match_id=request.decision_match_id,
            candidate_name=candidate_name,
            candidate_location=candidate_location,
            masked_phone=mask_phone(request.phone_e164_snapshot),
            screening_questions=self._parse_questions(request),
            screening_context_hash=request.screening_context_hash,
            readiness=(
                OutreachReadiness.STALE if stale_reasons else OutreachReadiness.READY_FOR_EXECUTION
            ),
            stale_reasons=stale_reasons,
            created_at=request.created_at,
        )

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        original = getattr(exc, "orig", None)
        diagnostic = getattr(original, "diag", None)
        value = getattr(diagnostic, "constraint_name", None)
        return str(value) if value else None
