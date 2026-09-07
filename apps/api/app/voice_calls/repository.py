"""Persistence primitives only; callers own transactions and external authority checks."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.hunar.schemas import HunarCallStatus
from app.voice_calls.models import VoiceCallExecution


class VoiceCallRepository:
    """Guard state transitions on locked rows; never commit or invoke providers/services."""

    def get_execution(self, session: Session, execution_id: UUID) -> VoiceCallExecution | None:
        """Read one execution without implicitly creating work."""
        return session.get(VoiceCallExecution, execution_id)

    def get_execution_for_update(
        self, session: Session, execution_id: UUID
    ) -> VoiceCallExecution | None:
        """Lock and refresh the current execution for a guarded transition."""
        return session.execute(
            select(VoiceCallExecution)
            .where(VoiceCallExecution.id == execution_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def get_for_outreach(self, session: Session, outreach_id: UUID) -> VoiceCallExecution | None:
        """Resolve the unique execution belonging to an outreach request."""
        return session.execute(
            select(VoiceCallExecution).where(VoiceCallExecution.outreach_request_id == outreach_id)
        ).scalar_one_or_none()

    def get_by_provider_request_id(
        self, session: Session, provider_request_id: str
    ) -> VoiceCallExecution | None:
        """Resolve exact immutable request correlation evidence."""

        return session.execute(
            select(VoiceCallExecution).where(
                VoiceCallExecution.provider_request_id == provider_request_id
            )
        ).scalar_one_or_none()

    def get_by_provider_call_id(
        self, session: Session, provider_call_id: UUID
    ) -> VoiceCallExecution | None:
        """Resolve a provider call identity already observed by Module 6."""

        return session.execute(
            select(VoiceCallExecution).where(
                VoiceCallExecution.provider_call_id == provider_call_id
            )
        ).scalar_one_or_none()

    def insert_execution(
        self, session: Session, row: VoiceCallExecution
    ) -> tuple[VoiceCallExecution, bool]:
        """Converge only the outreach uniqueness race using the established savepoint pattern."""
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row, True
        except IntegrityError as exc:
            if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) != (
                "uq_voice_call_executions_outreach"
            ):
                raise
            existing = self.get_for_outreach(session, row.outreach_request_id)
            if existing is None:
                raise
            return existing, False

    def mark_submitted(
        self, row: VoiceCallExecution, call_id: UUID, initial_status: HunarCallStatus
    ) -> bool:
        """Persist acceptance only from QUEUED; never overwrite a terminal observation."""
        if row.status != "queued":
            return False
        row.status = "submitted"
        row.provider_call_id = call_id
        row.provider_initial_status = initial_status.value
        row.submitted_at = datetime.now(UTC)
        row.updated_at = row.submitted_at
        row.failure_code = None
        return True

    def mark_failed(self, row: VoiceCallExecution, code: str) -> bool:
        """Record a proven pre-side-effect or rejection failure only from QUEUED."""
        if row.status != "queued":
            return False
        row.status = "failed"
        row.failure_code = code
        row.updated_at = datetime.now(UTC)
        return True

    def mark_unknown(
        self,
        row: VoiceCallExecution,
        code: str,
        call_id: UUID | None = None,
        initial_status: HunarCallStatus | None = None,
    ) -> bool:
        """Preserve safely observed identity, never downgrade SUBMITTED or FAILED."""
        if row.status not in {"queued", "unknown"}:
            return False
        if row.status == "unknown" and call_id is None:
            return False
        row.status = "unknown"
        row.failure_code = row.failure_code or code
        row.provider_call_id = row.provider_call_id or call_id
        row.provider_initial_status = row.provider_initial_status or (
            initial_status.value if initial_status else None
        )
        row.updated_at = datetime.now(UTC)
        return True

    def reset_failed_to_queued(self, row: VoiceCallExecution) -> bool:
        """Explicit retry changes operational state only, never frozen execution inputs."""
        if row.status != "failed":
            return False
        row.status = "queued"
        row.failure_code = None
        row.provider_initial_status = None
        row.updated_at = datetime.now(UTC)
        return True
