"""Module 7 signature, provider-contract, human-gate, mapping, and recovery invariants."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.call_results.dependencies import get_call_result_service
from app.call_results.errors import CallResultError
from app.call_results.models import VoiceCallResult, VoiceScreeningAnswer
from app.call_results.schemas import (
    ScreeningAnswerState,
    ScreeningResultState,
    TerminalCallEvidence,
    get_screening_result_contract,
)
from app.call_results.service import CallResultService, ClassifiedScreening
from app.core.config import Settings, get_settings
from app.integrations.hunar.schemas import HunarCallSummaryWebhook
from app.integrations.hunar.webhook_security import (
    HunarWebhookAuthenticationError,
    verify_hunar_webhook_signature,
)
from app.main import create_app
from app.outreach.schemas import OutreachScreeningQuestion
from app.voice_calls.agent_contract import RESULT_SCHEMA_JSON
from app.voice_calls.schemas import VoiceCallResultBinding


def signed(raw: bytes, timestamp: str, key: str) -> str:
    """Create the documented timestamp-dot-body Base64 HMAC for tests."""

    digest = hmac.new(key.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def result_payload(count: int = 1) -> dict[str, str]:
    """Return one exact v1 result with all unused slots explicitly inapplicable."""

    payload = {
        "conversation_outcome": "completed",
        "candidate_interest": "interested",
        "notes": " factual note ",
    }
    for position in range(1, 11):
        payload[f"question_{position}_answer"] = (
            f"answer {position}" if position <= count else "NOT_APPLICABLE"
        )
    return payload


def evidence(**changes: object) -> TerminalCallEvidence:
    """Create trusted-looking terminal evidence and selectively vary one contract field."""

    raw: dict[str, object] = {
        "provider_call_id": uuid4(),
        "provider_request_id": "hha-request",
        "agent_id": uuid4(),
        "mobile_number": "+12025550123",
        "provider_status": "COMPLETED",
        "lifecycle_status": "COMPLETED",
        "answered_by": "HUMAN",
        "max_retries": 0,
        "retry_count": 0,
        "retries_left": 0,
        "next_retry_scheduled_at": None,
        "timezone": "Asia/Kolkata",
        "duration_seconds": 10,
        "started_at": datetime(2026, 9, 7, tzinfo=UTC),
        "ended_at": datetime(2026, 9, 7, 0, 0, 10, tzinfo=UTC),
        "recording_url": "https://recordings.example/call",
        "provider_result": result_payload(),
    }
    raw.update(changes)
    return TerminalCallEvidence.model_validate(raw)


def binding(item: TerminalCallEvidence, **changes: object) -> VoiceCallResultBinding:
    """Bind evidence to one immutable Module 6 execution identity."""

    raw: dict[str, object] = {
        "execution_id": uuid4(),
        "outreach_request_id": uuid4(),
        "execution_status": "submitted",
        "agent_id": item.agent_id,
        "language": "ENGLISH",
        "timezone": "Asia/Kolkata",
        "agent_contract_version": "hunar_voice_screening_en_v1",
        "provider_request_id": item.provider_request_id,
        "provider_call_id": item.provider_call_id,
        "expected_mobile_number": item.mobile_number,
    }
    raw.update(changes)
    return VoiceCallResultBinding.model_validate(raw)


def questions(count: int) -> list[OutreachScreeningQuestion]:
    """Create exact immutable Module 5 question identities in a known order."""

    return [
        OutreachScreeningQuestion(
            id=uuid4(),
            source_job_question_id=None,
            key=f"question_{position}",
            prompt=f"Question {position}?",
            answer_type="short_text",
            required=True,
            options=[],
        )
        for position in range(1, count + 1)
    ]


def stored_result(*, state: str = "unavailable") -> VoiceCallResult:
    """Build a persisted-looking terminal row for semantic convergence tests."""

    now = datetime.now(UTC)
    return VoiceCallResult(
        id=uuid4(),
        voice_call_execution_id=uuid4(),
        provider_call_id=uuid4(),
        provider_status="COMPLETED",
        lifecycle_status="COMPLETED",
        answered_by=None if state == "unavailable" else "HUMAN",
        screening_result_state=state,
        result_failure_code=("HUNAR_RESULT_UNAVAILABLE" if state == "unavailable" else None),
        conversation_outcome="completed" if state == "available" else None,
        candidate_interest="interested" if state == "available" else None,
        notes="factual note" if state == "available" else None,
        duration_seconds=None,
        started_at=None,
        ended_at=None,
        recording_url=None,
        observed_at=now,
        updated_at=now,
        answers=[],
    )


class RecordingRepository:
    """Record service-authorized persistence calls without a database."""

    def __init__(self) -> None:
        self.inserted: list[VoiceScreeningAnswer] = []
        self.enriched = 0

    def insert_answers(self, session, answers) -> None:
        self.inserted.extend(answers)

    def enrich_result(self, session, row) -> None:
        self.enriched += 1


def convergence_service(repository: RecordingRepository) -> CallResultService:
    """Build a service used only for pure semantic convergence tests."""

    return CallResultService(
        object(),
        settings=Settings(database_url="postgresql://test"),
        provider=None,
        repository=repository,
    )


def test_signature_uses_exact_raw_bytes_multiple_signatures_and_keys() -> None:
    raw = b'{"event_type":"call_summary", "value":1}'
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signature = signed(raw, timestamp, "rotated-key")
    verify_hunar_webhook_signature(
        raw_body=raw,
        timestamp=timestamp,
        signature_header=f"bad,{signature}",
        trusted_keys=("old-key", "rotated-key"),
    )
    with pytest.raises(HunarWebhookAuthenticationError):
        verify_hunar_webhook_signature(
            raw_body=raw.replace(b", ", b","),
            timestamp=timestamp,
            signature_header=signature,
            trusted_keys=("rotated-key",),
        )


@pytest.mark.parametrize("offset", [-301, 301])
def test_signature_rejects_replayed_and_future_timestamps(offset: int) -> None:
    now = datetime.now(UTC)
    timestamp = str(int((now + timedelta(seconds=offset)).timestamp()))
    with pytest.raises(HunarWebhookAuthenticationError):
        verify_hunar_webhook_signature(
            raw_body=b"{}",
            timestamp=timestamp,
            signature_header=signed(b"{}", timestamp, "key"),
            trusted_keys=("key",),
            now=now,
        )


@pytest.mark.parametrize(
    "timestamp,signature,keys", [(None, "x", ("k",)), ("1", None, ("k",)), ("1", "x", ())]
)
def test_signature_requires_timestamp_signature_and_key(timestamp, signature, keys) -> None:
    with pytest.raises(HunarWebhookAuthenticationError):
        verify_hunar_webhook_signature(
            raw_body=b"{}", timestamp=timestamp, signature_header=signature, trusted_keys=keys
        )


def test_summary_parsing_and_normalization_are_exact() -> None:
    item = evidence()
    raw = {
        "event_type": "call_summary",
        "call_id": str(item.provider_call_id),
        "agent_id": str(item.agent_id),
        "request_id": item.provider_request_id,
        "to_number": item.mobile_number,
        "status": "COMPLETED",
        "lifecycle_status": "COMPLETED",
        "answered_by": "HUMAN",
        "max_retries": 0,
        "retry_count": 0,
        "retries_left": 0,
        "next_retry_scheduled_at": None,
        "timezone": "Asia/Kolkata",
        "result": result_payload(),
    }
    summary = HunarCallSummaryWebhook.model_validate(raw)
    assert TerminalCallEvidence.from_summary(summary).provider_request_id == "hha-request"
    with pytest.raises(ValidationError):
        HunarCallSummaryWebhook.model_validate({**raw, "event_type": "call_status_updated"})


def test_v1_result_contract_matches_module_6_schema_exactly() -> None:
    contract = get_screening_result_contract("hunar_voice_screening_en_v1")
    assert contract.expected_keys == frozenset(json.loads(RESULT_SCHEMA_JSON))
    assert contract.expected_keys == frozenset(result_payload())
    with pytest.raises(CallResultError):
        get_screening_result_contract("future_contract")


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_retries", 1),
        ("retry_count", 1),
        ("retries_left", 1),
        ("next_retry_scheduled_at", datetime.now(UTC)),
    ],
)
def test_retry_policy_conflicts_fail_closed(field: str, value: object) -> None:
    item = evidence(**{field: value})
    with pytest.raises(CallResultError) as caught:
        CallResultService._validate_evidence(binding(item), item)
    assert caught.value.code == "HUNAR_RETRY_POLICY_CONFLICT"


@pytest.mark.parametrize(
    "answered_by,code",
    [
        ("MACHINE", "HUNAR_SCREENING_ANSWERED_BY_MACHINE"),
        ("UNKNOWN", "HUNAR_SCREENING_HUMAN_NOT_CONFIRMED"),
        (None, "HUNAR_SCREENING_HUMAN_NOT_CONFIRMED"),
    ],
)
def test_nonhuman_completed_calls_never_create_answers(answered_by, code) -> None:
    item = evidence(answered_by=answered_by)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.state == ScreeningResultState.UNAVAILABLE
    assert classified.failure_code == code and classified.answers == ()


@pytest.mark.parametrize("lifecycle", ["NOT_CONNECTED", "FAILED", "CANCELLED"])
def test_noncompleted_terminal_calls_are_unavailable(lifecycle: str) -> None:
    item = evidence(lifecycle_status=lifecycle, provider_status=lifecycle)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.state == ScreeningResultState.UNAVAILABLE and not classified.answers


@pytest.mark.parametrize("count", [1, 10])
def test_exact_question_boundaries_and_uuid_order(count: int) -> None:
    item = evidence(provider_result=result_payload(count))
    historical = questions(count)
    classified = CallResultService._classify(binding(item), item, historical)
    assert classified.state == ScreeningResultState.AVAILABLE
    assert [answer[0] for answer in classified.answers] == [question.id for question in historical]


@pytest.mark.parametrize(
    "value,state,text",
    [
        ("NO_CLEAR_ANSWER", "no_clear_answer", None),
        ("NOT_ASKED", "not_asked", None),
        ("  factual answer  ", "answered", "factual answer"),
    ],
)
def test_configured_slot_sentinel_mapping(value: str, state: str, text: str | None) -> None:
    payload = result_payload()
    payload["question_1_answer"] = value
    item = evidence(provider_result=payload)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.answers[0][2].value == state and classified.answers[0][3] == text


@pytest.mark.parametrize(
    "value,state,text",
    [
        (5, "answered", "5"),
        (True, "answered", "true"),
        (None, "no_clear_answer", None),
        ("", "no_clear_answer", None),
        ("NOT_APPLICABLE", "not_asked", None),
    ],
)
def test_provider_answer_values_are_normalized_for_display(value, state, text) -> None:
    payload = result_payload()
    payload["question_1_answer"] = value
    item = evidence(provider_result=payload)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.state == "available"
    assert classified.answers[0][2].value == state
    assert classified.answers[0][3] == text


def test_unused_slots_and_extra_provider_fields_do_not_hide_configured_answers() -> None:
    change = {"qualified": "yes", "question_2_answer": "unexpected"}
    payload = {**result_payload(), **change}
    item = evidence(provider_result=payload)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.state == "available"
    assert len(classified.answers) == 1


def test_unknown_summary_labels_fall_back_without_hiding_answers() -> None:
    payload = {
        **result_payload(),
        "conversation_outcome": "provider_new_value",
        "candidate_interest": None,
    }
    item = evidence(provider_result=payload)
    classified = CallResultService._classify(binding(item), item, questions(1))
    assert classified.state == "available"
    assert classified.conversation_outcome == "other"
    assert classified.candidate_interest == "unclear"


def test_unavailable_monotonically_enriches_to_available_once() -> None:
    repository = RecordingRepository()
    service = convergence_service(repository)
    row = stored_result()
    incoming = stored_result(state="available")
    incoming.id = row.id
    incoming.voice_call_execution_id = row.voice_call_execution_id
    incoming.provider_call_id = row.provider_call_id
    incoming.duration_seconds = 42
    classified = ClassifiedScreening(
        state=ScreeningResultState.AVAILABLE,
        failure_code=None,
        conversation_outcome="completed",
        candidate_interest="interested",
        notes="factual note",
        answers=((uuid4(), 1, ScreeningAnswerState.ANSWERED, "Yes"),),
    )
    service._converge_existing(row, incoming, classified)
    assert row.screening_result_state == "available"
    assert row.answered_by == "HUMAN" and row.duration_seconds == 42
    assert len(repository.inserted) == 1 and repository.enriched == 1


def test_submillisecond_timestamp_truncation_is_not_a_terminal_conflict() -> None:
    repository = RecordingRepository()
    service = convergence_service(repository)
    row = stored_result()
    incoming = stored_result()
    incoming.voice_call_execution_id = row.voice_call_execution_id
    incoming.provider_call_id = row.provider_call_id
    row.started_at = datetime(2026, 9, 7, 10, 54, 25, 809710, tzinfo=UTC)
    incoming.started_at = datetime(2026, 9, 7, 10, 54, 25, 809000, tzinfo=UTC)
    classified = ClassifiedScreening(ScreeningResultState.INVALID, "HUNAR_RESULT_SCHEMA_INVALID")
    assert service._converge_existing(row, incoming, classified) is row

    incoming.started_at = datetime(2026, 9, 7, 10, 54, 25, 808000, tzinfo=UTC)
    with pytest.raises(CallResultError) as caught:
        service._converge_existing(row, incoming, classified)
    assert caught.value.code == "HUNAR_TERMINAL_EVIDENCE_CONFLICT"


def test_available_duplicate_is_idempotent_but_conflicting_answers_fail() -> None:
    repository = RecordingRepository()
    service = convergence_service(repository)
    row = stored_result(state="available")
    question_id = uuid4()
    row.answers = [
        VoiceScreeningAnswer(
            id=uuid4(),
            voice_call_result_id=row.id,
            outreach_question_id=question_id,
            position=1,
            answer_state="answered",
            answer_text="Yes",
        )
    ]
    incoming = stored_result(state="available")
    incoming.voice_call_execution_id = row.voice_call_execution_id
    incoming.provider_call_id = row.provider_call_id
    same = ClassifiedScreening(
        ScreeningResultState.AVAILABLE,
        None,
        "completed",
        "interested",
        "factual note",
        ((question_id, 1, ScreeningAnswerState.ANSWERED, "Yes"),),
    )
    assert service._converge_existing(row, incoming, same) is row
    conflicting = ClassifiedScreening(
        ScreeningResultState.AVAILABLE,
        None,
        "completed",
        "interested",
        "factual note",
        ((question_id, 1, ScreeningAnswerState.ANSWERED, "No"),),
    )
    with pytest.raises(CallResultError) as caught:
        service._converge_existing(row, incoming, conflicting)
    assert caught.value.code == "HUNAR_TERMINAL_EVIDENCE_CONFLICT"


def test_recording_reference_is_validated_and_never_exposed() -> None:
    assert CallResultService._safe_recording_url("http://recordings.example/x") is None
    assert CallResultService._safe_recording_url("https://user:secret@example/x") is None
    row = stored_result()
    row.recording_url = "https://recordings.example/x"
    response = CallResultService._to_response(row)
    assert response.recording_available is True
    assert "recording_url" not in response.model_dump()


def test_failed_module_6_and_identity_conflicts_fail_closed() -> None:
    item = evidence()
    with pytest.raises(CallResultError) as caught:
        CallResultService._validate_evidence(binding(item, execution_status="failed"), item)
    assert caught.value.code == "HUNAR_EXECUTION_STATE_CONFLICT"
    with pytest.raises(CallResultError) as caught:
        CallResultService._validate_evidence(
            binding(item, expected_mobile_number="+12025550124"), item
        )
    assert caught.value.code == "HUNAR_EXECUTION_CORRELATION_CONFLICT"


def test_webhook_verifies_before_parse_and_calls_finalizer_only_after_valid_json(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HUNAR_WEBHOOK_API_KEYS_JSON", '["webhook-key"]')
    get_settings.cache_clear()
    calls: list[TerminalCallEvidence] = []

    class FakeService:
        def finalize_terminal_evidence(self, item: TerminalCallEvidence) -> None:
            calls.append(item)

    app = create_app()
    app.dependency_overrides[get_call_result_service] = lambda: FakeService()
    client = TestClient(app)
    timestamp = str(int(datetime.now(UTC).timestamp()))
    invalid = b"not-json"
    response = client.post(
        "/api/v1/webhooks/hunar/call-summary",
        content=invalid,
        headers={
            "X-Hunar-Timestamp": timestamp,
            "X-Hunar-Signature": "invalid",
        },
    )
    assert response.status_code == 401 and not calls
    response = client.post(
        "/api/v1/webhooks/hunar/call-summary",
        content=invalid,
        headers={
            "X-Hunar-Timestamp": timestamp,
            "X-Hunar-Signature": signed(invalid, timestamp, "webhook-key"),
        },
    )
    assert response.status_code == 400 and not calls
    get_settings.cache_clear()
