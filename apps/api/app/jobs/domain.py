"""Pure Job-domain invariants shared by Job-owned downstream workflows."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.jobs.errors import ScreeningQuestionIdentityError


class QuestionWithKey(Protocol):
    """Structural contract required by the duplicate question-key invariant."""

    key: str


def assert_unique_screening_question_keys(questions: Iterable[QuestionWithKey]) -> None:
    """Reject duplicate canonical question keys with the stable Job-domain error."""

    seen: set[str] = set()
    for question in questions:
        if question.key in seen:
            raise ScreeningQuestionIdentityError(
                code="SCREENING_QUESTION_KEY_DUPLICATE",
                message="Screening question keys must be unique within a Job.",
                details={"key": question.key},
            )
        seen.add(question.key)
