"""Contract tests for the constrained Gemini Candidate matching adapter."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from app.core.retry import ProviderInvalidResponseError
from app.integrations.gemini.candidate_matching import GeminiCandidateMatchProvider
from app.matching.schemas import MatchInputSnapshot, SemanticEvidenceItem


def snapshot() -> MatchInputSnapshot:
    """Return one matching input that contains no Candidate contact PII."""

    return MatchInputSnapshot(
        job_id=uuid4(),
        definition_version=1,
        job_title="Senior Backend Engineer",
        alternate_titles=["Backend Engineer"],
        seniority=["senior"],
        candidate_id=uuid4(),
        candidate_current_title="Platform Engineer",
    )


def completed_body(payload: dict[str, object]) -> dict[str, object]:
    """Wrap structured JSON in the Gemini Interactions response shape."""

    return {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps(payload)}],
            }
        ],
    }


def test_adapter_sends_only_bounded_title_evidence_and_parses_schema() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json=completed_body(
                {
                    "role_alignment": {
                        "status": "supported",
                        "evidence_ids": ["E1"],
                        "reason": "Explicit title evidence is role-aligned.",
                    },
                    "seniority_alignment": {
                        "status": "unknown",
                        "evidence_ids": [],
                        "reason": "Seniority is not established.",
                    },
                }
            ),
        )

    provider = GeminiCandidateMatchProvider(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    result = provider.analyze(
        snapshot=snapshot(),
        evidence=[
            SemanticEvidenceItem(
                id="E1",
                title="Platform Engineer",
                source="candidate_current_title",
            )
        ],
    )

    prompt = str(captured["input"])
    assert result.role_alignment.status.value == "supported"
    assert "Platform Engineer" in prompt
    assert "Do not infer skills" in prompt
    assert "Do not calculate a score" in prompt
    assert "email" not in prompt.casefold()
    assert "phone" not in prompt.casefold()


def test_adapter_rejects_malformed_structured_output() -> None:
    provider = GeminiCandidateMatchProvider(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(  # noqa: ARG005
                200,
                json=completed_body({"role_alignment": {"status": "supported"}}),
            )
        ),
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.analyze(
            snapshot=snapshot(),
            evidence=[
                SemanticEvidenceItem(
                    id="E1",
                    title="Platform Engineer",
                    source="candidate_current_title",
                )
            ],
        )


def test_adapter_includes_temporal_context_and_canonical_precedence_guidance() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json=completed_body(
                {
                    "role_alignment": {
                        "status": "unknown",
                        "evidence_ids": [],
                        "reason": "Evidence is insufficient.",
                    },
                    "seniority_alignment": {
                        "status": "unknown",
                        "evidence_ids": [],
                        "reason": "Evidence is insufficient.",
                    },
                }
            ),
        )

    provider = GeminiCandidateMatchProvider(
        api_key="test-key",
        model="gemini-test",
        transport=httpx.MockTransport(handler),
    )
    provider.analyze(
        snapshot=snapshot(),
        evidence=[
            SemanticEvidenceItem(
                id="E1",
                title="Backend Engineer",
                source="employment_history",
                started_at="2021-04-01",
                is_current=False,
            )
        ],
    )

    prompt = str(captured["input"])
    assert "started_at=2021-04-01" in prompt
    assert "is_current=False" in prompt
    assert "Candidate Core current-title evidence is canonical" in prompt
    assert "do not establish total years" in prompt
