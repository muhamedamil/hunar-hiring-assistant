"""Finalize trusted evidence while preserving Module 5/6 authority and GET-only recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.call_results.errors import CallResultError
from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer
from app.call_results.repository import CallResultRepository
from app.call_results.schemas import (
    TERMINAL_LIFECYCLES,
    TERMINAL_PROVIDER_STATUSES,
    ReconciliationResponse,
    ScreeningAnswerState,
    ScreeningResultState,
    ScreeningResultV1,
    TerminalCallEvidence,
    VoiceCallResultResponse,
    VoiceScreeningAnswerResponse,
    get_screening_result_contract,
)
from app.core.config import Settings
from app.core.retry import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderTransientError,
    ProviderTransportError,
)
from app.integrations.hunar.client import HunarVoiceProvider
from app.integrations.hunar.schemas import HunarAnsweredBy, HunarLifecycleStatus
from app.outreach.schemas import OutreachScreeningQuestion
from app.outreach.service import OutreachService
from app.voice_calls.schemas import VoiceCallResultBinding
from app.voice_calls.service import VoiceCallService


@dataclass(frozen=True)
class ClassifiedScreening:
    """Validated persistence fields and their complete historical answer mapping."""

    state: ScreeningResultState
    failure_code: str | None
    conversation_outcome: str | None = None
    candidate_interest: str | None = None
    notes: str | None = None
    answers: tuple[tuple[UUID, int, ScreeningAnswerState, str | None], ...] = ()


class CallResultService:
    """Own Module 7 transactions; never mutate submission, Candidate, shortlist, or Job truth."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings,
        provider: HunarVoiceProvider | None,
        repository: CallResultRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._provider = provider
        self._repository = repository or CallResultRepository()

    def get_result(self, execution_id: UUID) -> VoiceCallResultResponse | None:
        """Return locally persisted terminal truth without performing provider HTTP."""

        with self._session.begin():
            row = self._repository.get_result_for_execution(self._session, execution_id)
            return self._to_response(row) if row is not None else None

    def finalize_terminal_evidence(self, evidence: TerminalCallEvidence) -> VoiceCallResultResponse:
        """Validate and durably converge trusted evidence through one normalized path."""

        with self._session.begin():
            voice_service = VoiceCallService(self._session, settings=self._settings, provider=None)
            binding = voice_service.resolve_result_binding(
                provider_call_id=evidence.provider_call_id,
                provider_request_id=evidence.provider_request_id,
            )
            self._validate_evidence(binding, evidence)
            questions = (
                OutreachService(self._session)
                .get_result_context(binding.outreach_request_id)
                .screening_questions
            )
            classified = self._classify(binding, evidence, questions)
            row = self._persist(binding, evidence, classified)
            return self._to_response(row)

    def reconcile_execution(self, execution_id: UUID) -> ReconciliationResponse:
        """Perform at most one GET for a known call ID outside every database transaction."""

        with self._session.begin():
            existing = self._repository.get_result_for_execution(self._session, execution_id)
            if existing is not None and existing.screening_result_state == "available":
                return ReconciliationResponse(
                    state="already_finalized", result=self._to_response(existing)
                )
            binding = VoiceCallService(
                self._session, settings=self._settings, provider=None
            ).get_result_binding(execution_id)
            call_id = binding.provider_call_id
        if call_id is None:
            raise CallResultError("HUNAR_SAFE_RECONCILIATION_UNAVAILABLE")
        if self._provider is None:
            raise CallResultError("HUNAR_NOT_CONFIGURED", 503)
        try:
            detail = self._provider.get_call(call_id)
        except ProviderAuthenticationError:
            raise CallResultError("HUNAR_CONFIGURATION_FAILURE", 503) from None
        except (ProviderTransientError, ProviderTransportError):
            raise CallResultError("HUNAR_PROVIDER_READ_RETRYABLE", 503) from None
        except ProviderInvalidResponseError:
            raise CallResultError("HUNAR_CALL_RESPONSE_INVALID", 502) from None
        except ProviderPermanentError as exc:
            if exc.status_code == 404:
                raise CallResultError("HUNAR_CALL_NOT_FOUND", 404) from None
            if exc.status_code == 402:
                raise CallResultError("HUNAR_CONFIGURATION_FAILURE", 503) from None
            raise CallResultError("HUNAR_PROVIDER_READ_FAILED", 502) from None
        evidence = TerminalCallEvidence.from_detail(detail)
        if evidence.lifecycle_status not in TERMINAL_LIFECYCLES:
            return ReconciliationResponse(
                state="not_terminal",
                result=self._to_response(existing) if existing is not None else None,
            )
        result = self.finalize_terminal_evidence(evidence)
        return ReconciliationResponse(
            state="enriched" if existing is not None else "finalized", result=result
        )

    @staticmethod
    def _validate_evidence(binding: VoiceCallResultBinding, evidence: TerminalCallEvidence) -> None:
        """Enforce exact execution identity, terminality, timing, and frozen no-redial policy."""

        if binding.execution_status == "failed":
            raise CallResultError("HUNAR_EXECUTION_STATE_CONFLICT")
        if evidence.lifecycle_status not in TERMINAL_LIFECYCLES:
            raise CallResultError("HUNAR_CALL_NOT_TERMINAL")
        if evidence.provider_status not in TERMINAL_PROVIDER_STATUSES:
            raise CallResultError("HUNAR_PROVIDER_STATUS_NOT_TERMINAL")
        if (
            evidence.agent_id != binding.agent_id
            or evidence.mobile_number != binding.expected_mobile_number
            or (evidence.timezone is not None and evidence.timezone != binding.timezone)
        ):
            raise CallResultError("HUNAR_EXECUTION_CORRELATION_CONFLICT")
        if (
            binding.provider_call_id is not None
            and evidence.provider_call_id != binding.provider_call_id
        ):
            raise CallResultError("HUNAR_EXECUTION_CORRELATION_CONFLICT")
        if (
            evidence.max_retries != 0
            or evidence.retry_count != 0
            or evidence.retries_left != 0
            or evidence.next_retry_scheduled_at is not None
        ):
            raise CallResultError("HUNAR_RETRY_POLICY_CONFLICT")
        if (
            evidence.started_at is not None
            and evidence.ended_at is not None
            and evidence.ended_at < evidence.started_at
        ):
            raise CallResultError("HUNAR_TERMINAL_EVIDENCE_CONFLICT")

    @classmethod
    def _classify(
        cls,
        binding: VoiceCallResultBinding,
        evidence: TerminalCallEvidence,
        questions: list[OutreachScreeningQuestion],
    ) -> ClassifiedScreening:
        """Apply terminal/human gates, then parse using the stored execution contract version."""

        if evidence.lifecycle_status != HunarLifecycleStatus.COMPLETED:
            return ClassifiedScreening(ScreeningResultState.UNAVAILABLE, None)
        if evidence.answered_by == HunarAnsweredBy.MACHINE:
            return ClassifiedScreening(
                ScreeningResultState.UNAVAILABLE, "HUNAR_SCREENING_ANSWERED_BY_MACHINE"
            )
        if evidence.answered_by != HunarAnsweredBy.HUMAN:
            return ClassifiedScreening(
                ScreeningResultState.UNAVAILABLE, "HUNAR_SCREENING_HUMAN_NOT_CONFIRMED"
            )
        if not evidence.provider_result:
            return ClassifiedScreening(ScreeningResultState.UNAVAILABLE, "HUNAR_RESULT_UNAVAILABLE")
        contract = get_screening_result_contract(binding.agent_contract_version)
        try:
            parsed = contract.parse(evidence.provider_result)
            answers = cls._map_answers(parsed, questions)
        except (ValidationError, ValueError):
            return ClassifiedScreening(ScreeningResultState.INVALID, "HUNAR_RESULT_SCHEMA_INVALID")
        return ClassifiedScreening(
            ScreeningResultState.AVAILABLE,
            None,
            parsed.conversation_outcome.value,
            parsed.candidate_interest.value,
            parsed.notes.strip() or None,
            answers,
        )

    @staticmethod
    def _map_answers(
        result: ScreeningResultV1, questions: list[OutreachScreeningQuestion]
    ) -> tuple[tuple[UUID, int, ScreeningAnswerState, str | None], ...]:
        """Map configured numbered slots to exact Module 5 UUIDs and display states."""

        mapped: list[tuple[UUID, int, ScreeningAnswerState, str | None]] = []
        for position in range(1, 11):
            value = getattr(result, f"question_{position}_answer")
            if position > len(questions):
                continue
            question = questions[position - 1]
            if value in (None, "NO_CLEAR_ANSWER"):
                state, answer_text = ScreeningAnswerState.NO_CLEAR_ANSWER, None
            elif value in ("NOT_ASKED", "NOT_APPLICABLE"):
                state, answer_text = ScreeningAnswerState.NOT_ASKED, None
            else:
                state, answer_text = ScreeningAnswerState.ANSWERED, value
            mapped.append((question.id, position, state, answer_text))
        return tuple(mapped)

    def _persist(
        self,
        binding: VoiceCallResultBinding,
        evidence: TerminalCallEvidence,
        classified: ClassifiedScreening,
    ) -> VoiceCallResult:
        """Insert or monotonically enrich one row while rejecting conflicting provider truth."""

        now = datetime.now(UTC)
        candidate = VoiceCallResult(
            voice_call_execution_id=binding.execution_id,
            provider_call_id=evidence.provider_call_id,
            provider_status=evidence.provider_status.value,
            lifecycle_status=evidence.lifecycle_status.value,
            answered_by=evidence.answered_by.value if evidence.answered_by else None,
            screening_result_state=classified.state.value,
            result_failure_code=classified.failure_code,
            conversation_outcome=classified.conversation_outcome,
            candidate_interest=classified.candidate_interest,
            notes=classified.notes,
            duration_seconds=evidence.duration_seconds,
            started_at=evidence.started_at,
            ended_at=evidence.ended_at,
            recording_url=self._safe_recording_url(evidence.recording_url),
            observed_at=now,
            updated_at=now,
        )
        row, inserted = self._repository.insert_result(self._session, candidate)
        if not inserted:
            row = self._converge_existing(row, candidate, classified)
        elif classified.answers:
            self._insert_answers(row, classified)
        return row

    def _converge_existing(
        self,
        row: VoiceCallResult,
        incoming: VoiceCallResult,
        classified: ClassifiedScreening,
    ) -> VoiceCallResult:
        if (
            row.voice_call_execution_id != incoming.voice_call_execution_id
            or row.provider_call_id != incoming.provider_call_id
            or row.provider_status != incoming.provider_status
            or row.lifecycle_status != incoming.lifecycle_status
        ):
            raise CallResultError("HUNAR_TERMINAL_EVIDENCE_CONFLICT")
        for field in ("answered_by", "duration_seconds", "started_at", "ended_at"):
            current, observed = getattr(row, field), getattr(incoming, field)
            if (
                current is not None
                and observed is not None
                and not self._equivalent_terminal_value(field, current, observed)
            ):
                raise CallResultError("HUNAR_TERMINAL_EVIDENCE_CONFLICT")
            if current is None and observed is not None:
                setattr(row, field, observed)
        if incoming.recording_url is not None:
            row.recording_url = incoming.recording_url
        if row.screening_result_state == "available":
            if classified.state == ScreeningResultState.AVAILABLE:
                self._assert_same_available(row, classified)
        elif classified.state == ScreeningResultState.AVAILABLE:
            row.screening_result_state = "available"
            row.result_failure_code = None
            row.conversation_outcome = classified.conversation_outcome
            row.candidate_interest = classified.candidate_interest
            row.notes = classified.notes
            self._insert_answers(row, classified)
        row.updated_at = datetime.now(UTC)
        self._repository.enrich_result(self._session, row)
        return row

    @staticmethod
    def _equivalent_terminal_value(field: str, current: object, observed: object) -> bool:
        """Treat sub-millisecond provider timestamp truncation as the same instant."""

        if field in {"started_at", "ended_at"}:
            return (
                isinstance(current, datetime)
                and isinstance(observed, datetime)
                and abs(current - observed) < timedelta(milliseconds=1)
            )
        return current == observed

    def _insert_answers(self, row: VoiceCallResult, classified: ClassifiedScreening) -> None:
        answers = [
            VoiceScreeningAnswer(
                voice_call_result_id=row.id,
                outreach_question_id=question_id,
                position=position,
                answer_state=state.value,
                answer_text=text,
            )
            for question_id, position, state, text in classified.answers
        ]
        self._repository.insert_answers(self._session, answers)
        row.answers = answers

    @staticmethod
    def _assert_same_available(row: VoiceCallResult, classified: ClassifiedScreening) -> None:
        values = (row.conversation_outcome, row.candidate_interest, row.notes)
        if values != (
            classified.conversation_outcome,
            classified.candidate_interest,
            classified.notes,
        ):
            raise CallResultError("HUNAR_TERMINAL_EVIDENCE_CONFLICT")
        current = tuple(
            (answer.outreach_question_id, answer.position, answer.answer_state, answer.answer_text)
            for answer in sorted(row.answers, key=lambda value: value.position)
        )
        expected = tuple(
            (question_id, position, state.value, text)
            for question_id, position, state, text in classified.answers
        )
        if current != expected:
            raise CallResultError("HUNAR_TERMINAL_EVIDENCE_CONFLICT")

    @staticmethod
    def _safe_recording_url(value: str | None) -> str | None:
        """Accept only hostful HTTPS references without embedded credentials."""

        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            return None
        return value

    @staticmethod
    def _to_response(row: VoiceCallResult) -> VoiceCallResultResponse:
        """Project database truth without exposing the backend-only recording URL."""

        return VoiceCallResultResponse.model_validate(
            {
                "id": row.id,
                "voice_call_execution_id": row.voice_call_execution_id,
                "provider_call_id": row.provider_call_id,
                "provider_status": row.provider_status,
                "lifecycle_status": row.lifecycle_status,
                "answered_by": row.answered_by,
                "screening_result_state": row.screening_result_state,
                "result_failure_code": row.result_failure_code,
                "conversation_outcome": row.conversation_outcome,
                "candidate_interest": row.candidate_interest,
                "notes": row.notes,
                "duration_seconds": row.duration_seconds,
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "recording_available": row.recording_url is not None,
                "observed_at": row.observed_at,
                "updated_at": row.updated_at,
                "answers": [
                    VoiceScreeningAnswerResponse.model_validate(answer) for answer in row.answers
                ],
            }
        )
