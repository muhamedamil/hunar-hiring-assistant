"""Worker certainty tests for credit-aware Apollo enrichment side effects."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.candidates.errors import CandidateIdentityConflictError
from app.core.config import Settings
from app.core.retry import (
    AmbiguousWorkError,
    PermanentWorkError,
    ProviderRateLimitError,
    ProviderTransportError,
    RetryableWorkError,
)
from app.sourcing.schemas import ProviderEnrichedPerson, ProviderEnrichmentResponse
from app.sourcing.workers import SourcingWorkHandlers
from app.work_items.models import WorkItem


class UncertainProvider:
    """Simulate a timeout after a credit-consuming request may have reached Apollo."""

    def enrich_person(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise ProviderTransportError(
            code="PROVIDER_TRANSPORT_UNCERTAIN",
            message="uncertain",
            operation_may_have_completed=True,
        )


class SuccessfulProvider:
    """Return one enriched Apollo person with a recoverable async request identifier."""

    def enrich_person(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return ProviderEnrichmentResponse(
            person=ProviderEnrichedPerson(
                external_person_id="person-1",
                full_name="Sarah Ahmed",
            ),
            request_id=-7,
        )


class RateLimitedProvider:
    """Simulate a provider rejection that is safe to retry after Retry-After."""

    def enrich_person(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise ProviderRateLimitError(
            code="PROVIDER_RATE_LIMITED",
            message="rate limited",
            status_code=429,
            retry_after_seconds=7,
        )


def work_item() -> WorkItem:
    """Return one synthetic running enrichment work item."""

    return WorkItem(
        id=uuid4(),
        work_type="apollo_people_enrichment",
        entity_type="sourcing_enrichment",
        entity_id=uuid4(),
        payload={},
        status="running",
        attempt_count=1,
        max_attempts=2,
    )


def handlers(provider) -> SourcingWorkHandlers:  # type: ignore[no-untyped-def]
    """Build handlers whose DB helpers are monkeypatched by individual tests."""

    settings = Settings(
        DATABASE_URL="postgresql://postgres:postgres@localhost/postgres",
        APOLLO_WEBHOOK_BASE_URL="https://api.example.test",
        APOLLO_WEBHOOK_SIGNING_SECRET="secret",
    )
    return SourcingWorkHandlers(
        session_factory=lambda: None,  # type: ignore[arg-type]
        provider=provider,
        settings=settings,
    )


def prepare_without_database(
    worker: SourcingWorkHandlers,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Replace DB-only helpers so tests isolate provider certainty classification."""

    transitions: list[str] = []
    monkeypatch.setattr(
        worker,
        "_load_enrichment_target",
        lambda enrichment_id: {"provider_person_id": "person-1"},
    )
    monkeypatch.setattr(worker, "_mark_requested", lambda enrichment_id: None)
    monkeypatch.setattr(
        worker,
        "_webhook_url",
        lambda enrichment_id: "https://example.test/webhook",
    )
    monkeypatch.setattr(
        worker,
        "_mark_unknown",
        lambda enrichment_id, code: transitions.append(f"unknown:{code}"),
    )
    monkeypatch.setattr(
        worker,
        "_record_retryable_failure",
        lambda enrichment_id, code, retry_after_seconds=None: transitions.append(
            f"retry:{code}:{retry_after_seconds}"
        ),
    )
    return transitions


def test_uncertain_enrichment_transport_becomes_unknown_not_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(UncertainProvider())
    transitions = prepare_without_database(worker, monkeypatch)

    with pytest.raises(AmbiguousWorkError):
        worker.handle_people_enrichment(work_item())

    assert transitions == ["unknown:PROVIDER_TRANSPORT_UNCERTAIN"]


def test_rate_limited_enrichment_is_safe_retry_with_provider_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(RateLimitedProvider())
    transitions = prepare_without_database(worker, monkeypatch)

    with pytest.raises(RetryableWorkError) as exc_info:
        worker.handle_people_enrichment(work_item())

    assert exc_info.value.retry_after_seconds == 7
    assert transitions == ["retry:APOLLO_ENRICHMENT_RATE_LIMITED:7"]


def test_safe_enrichment_retry_budget_exhaustion_marks_domain_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(RateLimitedProvider())
    transitions = prepare_without_database(worker, monkeypatch)
    monkeypatch.setattr(
        worker,
        "_mark_failed",
        lambda enrichment_id, code: transitions.append(f"failed:{code}"),
    )
    item = work_item()
    item.attempt_count = item.max_attempts

    with pytest.raises(PermanentWorkError) as exc_info:
        worker.handle_people_enrichment(item)

    assert exc_info.value.code == "APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED"
    assert transitions == ["failed:APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED"]


def test_missing_provider_marks_enrichment_failed_instead_of_leaving_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(None)
    transitions: list[str] = []
    monkeypatch.setattr(
        worker,
        "_mark_failed",
        lambda enrichment_id, code: transitions.append(code),
    )

    with pytest.raises(PermanentWorkError) as exc_info:
        worker.handle_people_enrichment(work_item())

    assert exc_info.value.code == "APOLLO_NOT_CONFIGURED"
    assert transitions == ["APOLLO_NOT_CONFIGURED"]


def test_candidate_identity_conflict_marks_enrichment_conflict_without_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(SuccessfulProvider())
    transitions = prepare_without_database(worker, monkeypatch)
    monkeypatch.setattr(
        worker,
        "_resolve_candidate",
        lambda person: (_ for _ in ()).throw(
            CandidateIdentityConflictError(candidate_ids={uuid4(), uuid4()})
        ),
    )
    monkeypatch.setattr(
        worker,
        "_mark_conflict",
        lambda enrichment_id: transitions.append("CANDIDATE_IDENTITY_CONFLICT"),
    )

    with pytest.raises(PermanentWorkError) as exc_info:
        worker.handle_people_enrichment(work_item())

    assert exc_info.value.code == "CANDIDATE_IDENTITY_CONFLICT"
    assert transitions == ["CANDIDATE_IDENTITY_CONFLICT"]


class RateLimitedPollProvider:
    """Simulate a rate-limited read-only poll observer."""

    def poll_enrichment(self, request_id: int):  # type: ignore[no-untyped-def]
        del request_id
        raise ProviderRateLimitError(
            code="PROVIDER_RATE_LIMITED",
            message="rate limited",
            status_code=429,
            retry_after_seconds=7,
        )


def poll_work_item() -> WorkItem:
    """Return one synthetic running zero-credit polling work item."""

    return WorkItem(
        id=uuid4(),
        work_type="apollo_enrichment_poll",
        entity_type="sourcing_enrichment",
        entity_id=uuid4(),
        payload={},
        status="running",
        attempt_count=1,
        max_attempts=2,
    )


def test_missing_poll_provider_does_not_terminally_fail_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(None)
    transitions: list[str] = []
    monkeypatch.setattr(
        worker,
        "_record_retryable_failure",
        lambda enrichment_id, code, retry_after_seconds=None: transitions.append(
            f"observer:{code}:{retry_after_seconds}"
        ),
    )
    monkeypatch.setattr(
        worker,
        "_mark_failed",
        lambda enrichment_id, code: transitions.append(f"failed:{code}"),
    )

    with pytest.raises(PermanentWorkError) as exc_info:
        worker.handle_enrichment_poll(poll_work_item())

    assert exc_info.value.code == "APOLLO_POLL_NOT_CONFIGURED"
    assert transitions == ["observer:APOLLO_POLL_NOT_CONFIGURED:None"]


def test_poll_retry_exhaustion_leaves_webhook_authority_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = handlers(RateLimitedPollProvider())
    transitions: list[str] = []
    monkeypatch.setattr(worker, "_load_poll_request_id", lambda enrichment_id: 123)
    monkeypatch.setattr(
        worker,
        "_record_retryable_failure",
        lambda enrichment_id, code, retry_after_seconds=None: transitions.append(
            f"observer:{code}:{retry_after_seconds}"
        ),
    )
    monkeypatch.setattr(
        worker,
        "_mark_failed",
        lambda enrichment_id, code: transitions.append(f"failed:{code}"),
    )
    item = poll_work_item()
    item.attempt_count = item.max_attempts

    with pytest.raises(PermanentWorkError) as exc_info:
        worker.handle_enrichment_poll(item)

    assert exc_info.value.code == "APOLLO_POLL_ATTEMPTS_EXHAUSTED"
    assert transitions == ["observer:APOLLO_POLL_ATTEMPTS_EXHAUSTED:None"]
