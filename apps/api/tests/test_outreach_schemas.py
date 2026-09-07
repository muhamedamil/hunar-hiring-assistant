"""Deterministic Module 5 screening hash and DTO boundary tests."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.outreach.schemas import OutreachScreeningQuestionDraft, PrepareOutreachRequest
from app.outreach.service import canonical_screening_context_hash


def draft(*, key: str, prompt: str, options: list[str] | None = None):
    return OutreachScreeningQuestionDraft(
        source_job_question_id=uuid4(),
        key=key,
        prompt=prompt,
        answer_type="choice" if options else "short_text",
        required=True,
        options=options or [],
    )


def test_screening_hash_is_stable_and_order_sensitive() -> None:
    first = draft(key="interest", prompt="Why are you interested in this role?")
    second = draft(key="notice", prompt="What is your notice period?")
    assert canonical_screening_context_hash([first, second]) == canonical_screening_context_hash(
        [first.model_copy(deep=True), second.model_copy(deep=True)]
    )
    assert canonical_screening_context_hash([first, second]) != canonical_screening_context_hash(
        [second, first]
    )


def test_screening_hash_changes_with_prompt_options_and_provenance() -> None:
    question = draft(
        key="location",
        prompt="Which work location do you prefer?",
        options=["Pune", "Mumbai"],
    )
    base = canonical_screening_context_hash([question])
    assert base != canonical_screening_context_hash(
        [question.model_copy(update={"prompt": "Which city do you prefer?"})]
    )
    assert base != canonical_screening_context_hash(
        [question.model_copy(update={"options": ["Mumbai", "Pune"]})]
    )
    assert base != canonical_screening_context_hash(
        [question.model_copy(update={"source_job_question_id": None})]
    )


def test_browser_contract_forbids_client_key_and_authoritative_fields() -> None:
    question = draft(key="interest", prompt="Why are you interested in this role?")
    payload = {
        "preparation_token": "a" * 64,
        "screening_questions": [{**question.model_dump(mode="json"), "client_key": "browser-only"}],
        "phone": "+919999999999",
    }
    with pytest.raises(ValidationError):
        PrepareOutreachRequest.model_validate(payload)
