"""Service-owned execution creation/retry transactions around read-only agent preflight."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.candidates.service import CandidateService
from app.core.config import Settings
from app.core.retry import (
    ProviderAuthenticationError,
    ProviderInvalidResponseError,
    ProviderPermanentError,
    ProviderTransientError,
    ProviderTransportError,
)
from app.integrations.hunar.client import HunarVoiceProvider
from app.integrations.hunar.schemas import (
    HunarCallbackConfig,
    HunarCallCreateCommand,
    HunarLanguage,
    HunarRetryConfig,
    HunarTimezone,
)
from app.jobs.schemas import ApprovedJobDefinition
from app.jobs.service import JobService
from app.outreach.schemas import OutreachScreeningQuestion
from app.outreach.service import OutreachService
from app.voice_calls.agent_contract import AgentContract, get_contract
from app.voice_calls.errors import VoiceCallError
from app.voice_calls.models import VoiceCallExecution
from app.voice_calls.repository import VoiceCallRepository
from app.voice_calls.schemas import VoiceCallExecutionResponse, VoiceScreeningOptionsResponse
from app.work_items.repository import WorkItemRepository
from app.work_items.schemas import WorkItemCreate
from app.work_items.service import WorkItemService

WORK_TYPE = "hunar_voice_call_dispatch"
ENTITY_TYPE = "voice_call_execution"


def build_role_context(definition: ApprovedJobDefinition) -> str:
    """Use only compact factual role fields from the exact bound immutable version."""
    requirements = definition.requirements
    lines = [f"Role title: {definition.title}"]
    for label, values in (
        ("Seniority", requirements.seniority),
        ("Locations", requirements.locations),
        ("Required skills", requirements.required_skills),
        ("Preferred skills", requirements.preferred_skills),
    ):
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    if requirements.min_years_experience is not None:
        lines.append(f"Minimum experience: {requirements.min_years_experience} years")
    if requirements.employment_type:
        lines.append(f"Employment type: {requirements.employment_type.value}")
    if requirements.work_arrangement:
        lines.append(f"Work arrangement: {requirements.work_arrangement.value}")
    return "\n".join(lines)


def build_screening_plan(questions: list[OutreachScreeningQuestion]) -> str:
    """Preserve exact Module 5 order and question text with compact conversation metadata."""
    blocks = []
    for number, question in enumerate(questions, 1):
        lines = [
            f"Question {number}",
            f"Key: {question.key}",
            f"Answer type: {question.answer_type.value}",
            f"Required: {'yes' if question.required else 'no'}",
        ]
        if question.options:
            lines.append(f"Options: {' | '.join(question.options)}")
        lines.append(f"Prompt: {question.prompt}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def preflight(provider: HunarVoiceProvider | None, agent_id: UUID, contract: AgentContract) -> None:
    """Perform read-only exact preflight; caller must have ended every DB transaction."""
    if provider is None:
        raise VoiceCallError("HUNAR_NOT_CONFIGURED", 503)
    try:
        agent = provider.get_agent(agent_id)
    except (ProviderTransientError, ProviderTransportError, ProviderInvalidResponseError):
        raise VoiceCallError("HUNAR_PREFLIGHT_RETRYABLE", 503) from None
    except (ProviderAuthenticationError, ProviderPermanentError):
        raise VoiceCallError("HUNAR_CONFIGURATION_FAILURE", 503) from None
    contract.validate(agent, agent_id)


def enqueue_execution(session: Session, execution_id: UUID) -> None:
    """Atomically enqueue one active dispatch with a bounded three-attempt budget."""
    WorkItemService().enqueue(
        session,
        WorkItemCreate(
            work_type=WORK_TYPE,
            entity_type=ENTITY_TYPE,
            entity_id=execution_id,
            dedupe_key=f"hunar-voice-call:{execution_id}",
            max_attempts=3,
            payload={},
        ),
    )


class VoiceCallService:
    """Module 5 owns outreach truth; this service owns only durable submission intent."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings,
        provider: HunarVoiceProvider | None,
        repository: VoiceCallRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._provider = provider
        self._repository = repository or VoiceCallRepository()

    def get_options(self) -> VoiceScreeningOptionsResponse:
        """Return configuration only; this operation never performs Hunar HTTP or DB reads."""
        bindings = self._settings.hunar_agent_ids
        return VoiceScreeningOptionsResponse(
            languages=[HunarLanguage.ENGLISH] if HunarLanguage.ENGLISH in bindings else [],
            default_language=self._settings.hunar_default_language,
            timezones=list(HunarTimezone),
            default_timezone=self._settings.hunar_default_timezone,
        )

    def create_execution(
        self, outreach_request_id: UUID, *, language: HunarLanguage, timezone: HunarTimezone
    ) -> VoiceCallExecutionResponse:
        """Preflight before inserting one frozen execution and its work item atomically."""
        contract = get_contract()
        if language != contract.language or language not in self._settings.hunar_agent_ids:
            raise VoiceCallError("HUNAR_LANGUAGE_NOT_CONFIGURED", 422)
        timezone = HunarTimezone(timezone)
        agent_id = self._settings.hunar_agent_ids[language]
        self._preflight(agent_id, contract)
        with self._session.begin():
            snapshot = OutreachService(self._session).lock_dispatchable_outreach(
                outreach_request_id
            )
            existing = self._repository.get_for_outreach(self._session, outreach_request_id)
            if existing is not None:
                return VoiceCallExecutionResponse.model_validate(existing)
            candidate = CandidateService(self._session).get_summaries_by_ids(
                {snapshot.candidate_id}
            )[snapshot.candidate_id]
            definition = JobService(self._session).get_definition_version(
                snapshot.job_id, snapshot.definition_version
            )
            execution_id = uuid4()
            command = HunarCallCreateCommand(
                agent_id=agent_id,
                callee_name=candidate.full_name,
                mobile_number=snapshot.phone_e164,
                custom_data={
                    "job_role": definition.title,
                    "role_context": build_role_context(definition),
                    "screening_plan": build_screening_plan(snapshot.screening_questions),
                },
                request_id=f"hha-{execution_id.hex}",
                timezone=timezone,
                retry_config=HunarRetryConfig(),
                callback_config=(
                    HunarCallbackConfig(
                        call_summary_callback_url=self._settings.hunar_call_summary_callback_url
                    )
                    if self._settings.hunar_call_summary_callback_url
                    else None
                ),
            )
            row, inserted = self._repository.insert_execution(
                self._session,
                VoiceCallExecution(
                    id=execution_id,
                    outreach_request_id=snapshot.outreach_request_id,
                    status="queued",
                    agent_id=agent_id,
                    language=language.value,
                    timezone=timezone.value,
                    agent_contract_version=contract.version,
                    provider_request_id=command.request_id,
                    provider_payload_snapshot=command.model_dump(mode="json", exclude_none=True),
                ),
            )
            if inserted:
                enqueue_execution(self._session, row.id)
            return VoiceCallExecutionResponse.model_validate(row)

    def get_execution(self, execution_id: UUID) -> VoiceCallExecutionResponse:
        """Return a public PII-free projection without provider lookups."""
        with self._session.begin():
            return VoiceCallExecutionResponse.model_validate(self._require(execution_id))

    def get_execution_for_outreach(
        self, outreach_request_id: UUID
    ) -> VoiceCallExecutionResponse | None:
        """Return null when no execution exists, supporting the existing outreach workflow."""
        with self._session.begin():
            row = self._repository.get_for_outreach(self._session, outreach_request_id)
            return VoiceCallExecutionResponse.model_validate(row) if row is not None else None

    def retry_failed_execution(self, execution_id: UUID) -> VoiceCallExecutionResponse:
        """FAILED only; preflight between two short transactions, reuse exact frozen payload."""
        with self._session.begin():
            row = self._require(execution_id)
            if row.status != "failed":
                raise VoiceCallError("VOICE_CALL_NOT_RETRYABLE")
            agent_id, version = row.agent_id, row.agent_contract_version
        self._preflight(agent_id, get_contract(version))
        with self._session.begin():
            row = self._require(execution_id, lock=True)
            if row.status != "failed":
                raise VoiceCallError("VOICE_CALL_NOT_RETRYABLE")
            OutreachService(self._session).lock_dispatchable_outreach(row.outreach_request_id)
            # A worker records domain FAILED before the runner completes its queue item.
            # Refuse this brief race (and UNKNOWN queue blockers) instead of orphaning QUEUED.
            active = WorkItemRepository().get_active_by_dedupe_key(
                self._session, f"hunar-voice-call:{row.id}"
            )
            if active is not None:
                raise VoiceCallError("VOICE_CALL_WORK_STILL_ACTIVE")
            self._repository.reset_failed_to_queued(row)
            self._session.flush()
            enqueue_execution(self._session, row.id)
            return VoiceCallExecutionResponse.model_validate(row)

    def _preflight(self, agent_id: UUID, contract: AgentContract) -> None:
        if self._session.in_transaction():
            raise RuntimeError("Provider preflight requires a closed transaction")
        preflight(self._provider, agent_id, contract)

    def _require(self, execution_id: UUID, *, lock: bool = False) -> VoiceCallExecution:
        row = (
            self._repository.get_execution_for_update(self._session, execution_id)
            if lock
            else self._repository.get_execution(self._session, execution_id)
        )
        if row is None:
            raise VoiceCallError("VOICE_CALL_NOT_FOUND", 404)
        return row
