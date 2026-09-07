"""Signature-first Hunar summary ingestion and PII-safe Module 7 result/recovery APIs."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.call_results.dependencies import get_call_result_service
from app.call_results.errors import CallResultError
from app.call_results.schemas import (
    ReconciliationResponse,
    TerminalCallEvidence,
    VoiceCallResultResponse,
)
from app.call_results.service import CallResultService
from app.core.config import get_settings
from app.integrations.hunar.schemas import HunarCallSummaryWebhook
from app.integrations.hunar.webhook_security import verify_hunar_webhook_signature

router = APIRouter(tags=["call-results"])
Service = Annotated[CallResultService, Depends(get_call_result_service)]


@router.post("/api/v1/webhooks/hunar/call-summary")
async def receive_call_summary(request: Request, service: Service) -> dict[str, bool]:
    """Authenticate exact raw bytes before JSON parsing, then commit terminal truth."""

    raw_body = await request.body()
    verify_hunar_webhook_signature(
        raw_body=raw_body,
        timestamp=request.headers.get("X-Hunar-Timestamp"),
        signature_header=request.headers.get("X-Hunar-Signature"),
        trusted_keys=get_settings().hunar_webhook_api_keys,
    )
    try:
        payload = json.loads(raw_body.decode("utf-8"))
        summary = HunarCallSummaryWebhook.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError):
        raise CallResultError("HUNAR_WEBHOOK_PAYLOAD_INVALID", 400) from None
    service.finalize_terminal_evidence(TerminalCallEvidence.from_summary(summary))
    return {"ok": True}


@router.get("/api/v1/voice-call-executions/{execution_id}/screening-result")
def get_screening_result(execution_id: UUID, service: Service) -> VoiceCallResultResponse | None:
    """Read application-owned terminal truth without calling Hunar."""

    return service.get_result(execution_id)


@router.post("/api/v1/voice-call-executions/{execution_id}/screening-result/reconcile")
def reconcile_screening_result(execution_id: UUID, service: Service) -> ReconciliationResponse:
    """Perform one explicit GET-only recovery when Module 6 knows the provider call ID."""

    return service.reconcile_execution(execution_id)
