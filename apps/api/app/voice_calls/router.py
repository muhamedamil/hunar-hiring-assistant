"""Five Module 6 endpoints extending immutable outreach; no lifecycle or callback API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.voice_calls.dependencies import get_voice_call_service
from app.voice_calls.schemas import (
    VoiceCallExecutionCreateRequest,
    VoiceCallExecutionResponse,
    VoiceScreeningOptionsResponse,
)
from app.voice_calls.service import VoiceCallService

router = APIRouter(tags=["voice-screening"])
Service = Annotated[VoiceCallService, Depends(get_voice_call_service)]


@router.get("/api/v1/voice-screening/options")
def get_options(service: Service) -> VoiceScreeningOptionsResponse:
    """Expose configured options without calling Hunar."""
    return service.get_options()


@router.post(
    "/api/v1/outreach-requests/{outreach_request_id}/voice-call-executions", status_code=202
)
def create_execution(
    outreach_request_id: UUID, request: VoiceCallExecutionCreateRequest, service: Service
) -> VoiceCallExecutionResponse:
    """Start or converge on the single execution of a dispatchable outreach request."""
    return service.create_execution(
        outreach_request_id, language=request.language, timezone=request.timezone
    )


@router.get("/api/v1/outreach-requests/{outreach_request_id}/voice-call-execution")
def get_for_outreach(
    outreach_request_id: UUID, service: Service
) -> VoiceCallExecutionResponse | None:
    """Return the existing safe projection, or null before Start."""
    return service.get_execution_for_outreach(outreach_request_id)


@router.get("/api/v1/voice-call-executions/{execution_id}")
def get_execution(execution_id: UUID, service: Service) -> VoiceCallExecutionResponse:
    """Read submission certainty without querying provider lifecycle."""
    return service.get_execution(execution_id)


@router.post("/api/v1/voice-call-executions/{execution_id}/retry", status_code=202)
def retry_execution(execution_id: UUID, service: Service) -> VoiceCallExecutionResponse:
    """Retry a known FAILED dispatch using its exact frozen inputs."""
    return service.retry_failed_execution(execution_id)
