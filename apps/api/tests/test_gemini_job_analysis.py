"""Contract tests for the Gemini Interactions API adapter using MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.retry import ProviderInvalidResponseError
from app.integrations.gemini.job_analysis import GeminiJobAnalysisProvider


def _success_response() -> dict[str, object]:
    proposal = {
        "suggested_title": "Senior Python Engineer",
        "requirements": {
            "alternate_titles": ["Backend Engineer"],
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["AWS"],
            "locations": ["Bangalore"],
            "min_years_experience": 5,
            "seniority": ["senior"],
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
        },
        "suggested_screening_questions": [
            {
                "key": "python_experience",
                "prompt": "How many years of Python experience do you have?",
                "answer_type": "number",
                "required": True,
                "options": [],
            }
        ],
    }
    return {
        "id": "int_test",
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps(proposal)}],
            }
        ],
    }


def test_gemini_uses_interactions_structured_output_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "secret-key"
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.7-flash"
        assert payload["generation_config"] == {"thinking_level": "low"}
        assert payload["response_format"]["mime_type"] == "application/json"
        schema = payload["response_format"]["schema"]
        assert schema["type"] == "object"
        assert set(schema["required"]) == {
            "suggested_title",
            "requirements",
            "suggested_screening_questions",
        }
        assert set(schema["$defs"]["ProposedJobRequirements"]["required"]) == {
            "alternate_titles",
            "required_skills",
            "preferred_skills",
            "locations",
            "min_years_experience",
            "seniority",
            "employment_type",
            "work_arrangement",
        }
        assert "BEGIN JOB DESCRIPTION" in payload["input"]
        assert "Return every field" in payload["input"]
        return httpx.Response(200, json=_success_response())

    provider = GeminiJobAnalysisProvider(
        api_key="secret-key",
        model="gemini-3.7-flash",
        transport=httpx.MockTransport(handler),
    )
    output = provider.analyze(
        title="Senior Python Engineer",
        description="Build reliable Python and FastAPI services for our hiring product.",
    )

    assert output.suggested_title == "Senior Python Engineer"
    assert output.requirements.required_skills == ["Python", "FastAPI"]


def test_gemini_rejects_incomplete_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "incomplete", "steps": []})
    )
    provider = GeminiJobAnalysisProvider(
        api_key="secret-key",
        model="gemini-3.7-flash",
        transport=transport,
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.analyze(
            title=None,
            description="A sufficiently long Job Description for provider validation.",
        )


def test_gemini_rejects_schema_invalid_output() -> None:
    body = {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps({"requirements": "bad"})}],
            }
        ]
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    provider = GeminiJobAnalysisProvider(
        api_key="secret-key",
        model="gemini-3.7-flash",
        transport=transport,
    )

    with pytest.raises(ProviderInvalidResponseError):
        provider.analyze(
            title=None,
            description="A sufficiently long Job Description for provider validation.",
        )
