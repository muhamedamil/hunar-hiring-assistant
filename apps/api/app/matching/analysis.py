"""Provider-neutral protocol for constrained semantic Candidate↔Job evidence classification."""

from __future__ import annotations

from typing import Protocol

from app.matching.schemas import MatchInputSnapshot, SemanticEvidenceItem, SemanticMatchOutput


class CandidateMatchProvider(Protocol):
    """Classify explicit title evidence without owning scoring or shortlist decisions."""

    @property
    def model_name(self) -> str:
        """Return the configured provider model identifier for audit and cache identity."""

    def analyze(
        self,
        *,
        snapshot: MatchInputSnapshot,
        evidence: list[SemanticEvidenceItem],
    ) -> SemanticMatchOutput:
        """Return evidence-citing role and seniority classifications."""
