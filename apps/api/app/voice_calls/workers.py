"""Durable Hunar submission with explicit side-effect certainty and UNKNOWN convergence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.core.retry import (
    AmbiguousWorkError,
    PermanentWorkError,
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    ProviderTransportError,
    RetryableWorkError,
)
from app.integrations.hunar.client import HunarVoiceProvider
from app.integrations.hunar.errors import HunarAmbiguousResponseError
from app.integrations.hunar.schemas import HunarCallCreateCommand, HunarCallStatus
from app.outreach.service import OutreachService
from app.voice_calls.agent_contract import get_contract
from app.voice_calls.errors import VoiceCallError
from app.voice_calls.repository import VoiceCallRepository
from app.voice_calls.service import ENTITY_TYPE, WORK_TYPE
from app.work_items.models import WorkItem


class VoiceCallWorkHandlers:
    """Submit each frozen payload only when repetition is demonstrably safe."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        provider: HunarVoiceProvider | None,
        settings: Settings,
        repository: VoiceCallRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._settings = settings
        self._repository = repository or VoiceCallRepository()

    def handle_dispatch(self, item: WorkItem) -> None:
        """Revalidate outreach, close DB, preflight, POST once, then persist certainty."""
        if item.entity_type != ENTITY_TYPE or item.entity_id is None:
            raise PermanentWorkError(code="INVALID_VOICE_WORK", message="Invalid execution work.")
        execution_id = item.entity_id
        with self._session_factory() as session, session.begin():
            row = self._repository.get_execution_for_update(session, execution_id)
            if row is None:
                raise PermanentWorkError(code="VOICE_CALL_NOT_FOUND", message="Execution missing.")
            if row.status != "queued":
                return
            try:
                OutreachService(session).lock_dispatchable_outreach(row.outreach_request_id)
            except AppError:
                self._repository.mark_failed(row, "OUTREACH_NOT_DISPATCHABLE")
                session.flush()
                return
            command = HunarCallCreateCommand.model_validate(row.provider_payload_snapshot)
            version, agent_id = row.agent_contract_version, row.agent_id
        # Every session above is closed before provider HTTP starts.
        if self._provider is None:
            self._fail(execution_id, "HUNAR_NOT_CONFIGURED")
        provider = self._provider
        try:
            get_contract(version).validate(provider.get_agent(agent_id), agent_id)
        except (
            ProviderTransientError,
            ProviderTransportError,
            ProviderInvalidResponseError,
        ) as exc:
            self._retry_or_fail(item, exc.code, getattr(exc, "retry_after_seconds", None))
        except (ProviderAuthenticationError, ProviderPermanentError, VoiceCallError):
            self._fail(execution_id, "HUNAR_PREFLIGHT_FAILED")
        # Expired leases must not enter the side effect even if GET eventually returned.
        if self._lease_expired(item):
            self._ambiguous(execution_id, "WORKER_LEASE_EXPIRED")
        observed_id = None
        observed_status = None
        try:
            result = provider.create_call(command)
            observed_id, observed_status = result.id, result.status
        except ProviderRateLimitError as exc:
            self._retry_or_fail(item, exc.code, exc.retry_after_seconds)
        except ProviderTransportError as exc:
            if not exc.operation_may_have_completed:
                self._retry_or_fail(item, exc.code)
            self._ambiguous(execution_id, exc.code)
        except HunarAmbiguousResponseError as exc:
            self._ambiguous(execution_id, exc.code, exc.call_id, exc.initial_status)
        except (ProviderTransientError, ProviderInvalidResponseError) as exc:
            self._ambiguous(execution_id, exc.code)
        except (ProviderAuthenticationError, ProviderPermanentError) as exc:
            if exc.status_code in {400, 401, 402, 404, 422}:
                self._fail(execution_id, exc.code)
            self._ambiguous(execution_id, "HUNAR_UNCLASSIFIED_HTTP_OUTCOME")
        except Exception:
            self._ambiguous(execution_id, "HUNAR_UNCLASSIFIED_POST_OUTCOME")
        if self._lease_expired(item):
            self._ambiguous(execution_id, "WORKER_LEASE_EXPIRED", observed_id, observed_status)
        try:
            with self._session_factory() as session, session.begin():
                row = self._repository.get_execution_for_update(session, execution_id)
                if row is None or not self._repository.mark_submitted(
                    row, result.id, result.status
                ):
                    raise RuntimeError("Execution state changed during submission")
                session.flush()
        except Exception:
            self._ambiguous(
                execution_id, "HUNAR_ACCEPTANCE_PERSISTENCE_UNCERTAIN", observed_id, observed_status
            )

    def reconcile_unknown_work(self) -> int:
        """Converge queue UNKNOWN plus domain QUEUED, preserving every terminal domain state."""
        count = 0
        with self._session_factory() as session, session.begin():
            items = session.execute(
                select(WorkItem).where(
                    WorkItem.work_type == WORK_TYPE,
                    WorkItem.entity_type == ENTITY_TYPE,
                    WorkItem.status == "unknown",
                    WorkItem.entity_id.is_not(None),
                )
            ).scalars()
            for item in items:
                assert item.entity_id is not None
                row = self._repository.get_execution_for_update(session, item.entity_id)
                if row is not None and row.status == "queued":
                    count += int(
                        self._repository.mark_unknown(
                            row, item.last_error_code or "HUNAR_WORK_UNKNOWN"
                        )
                    )
            session.flush()
        return count

    def _retry_or_fail(
        self, item: WorkItem, code: str, retry_after_seconds: float | None = None
    ) -> NoReturn:
        assert item.entity_id is not None
        if item.attempt_count >= item.max_attempts:
            self._fail(item.entity_id, "HUNAR_ATTEMPTS_EXHAUSTED")
        raise RetryableWorkError(
            code=code, message="Safe Hunar retry pending.", retry_after_seconds=retry_after_seconds
        ) from None

    def _fail(self, execution_id: UUID, code: str) -> NoReturn:
        with self._session_factory() as session, session.begin():
            row = self._repository.get_execution_for_update(session, execution_id)
            if row is not None:
                self._repository.mark_failed(row, code)
                session.flush()
        raise PermanentWorkError(code=code, message="Call could not be submitted.") from None

    def _ambiguous(
        self,
        execution_id: UUID,
        code: str,
        call_id: UUID | None = None,
        initial_status: HunarCallStatus | None = None,
    ) -> NoReturn:
        try:
            with self._session_factory() as session, session.begin():
                row = self._repository.get_execution_for_update(session, execution_id)
                if row is not None:
                    self._repository.mark_unknown(row, code, call_id, initial_status)
                    session.flush()
        except Exception:
            # Module 0 still makes the queue UNKNOWN; reconciliation later converges the domain.
            pass
        raise AmbiguousWorkError(
            code=code, message="Call submission outcome is uncertain."
        ) from None

    def _lease_expired(self, item: WorkItem) -> bool:
        return item.locked_at is None or datetime.now(UTC) >= (
            item.locked_at + timedelta(seconds=self._settings.worker_lease_seconds)
        )
