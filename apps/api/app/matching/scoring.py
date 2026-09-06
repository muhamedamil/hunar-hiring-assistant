"""Pure evidence normalization, criterion construction, hashing, and deterministic scoring."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.matching.schemas import (
    MatchCriterion,
    MatchCriterionStatus,
    MatchInputSnapshot,
    SemanticCriterionVerdict,
    SemanticEvidenceItem,
    SemanticMatchOutput,
)

MATCH_POLICY_VERSION = "candidate_job_match_v1"
SEMANTIC_PROMPT_VERSION = "candidate_match_semantic_v1"


@dataclass(frozen=True)
class MatchScore:
    """Deterministic aggregate score and evidence-coverage result."""

    match_score: int
    evidence_coverage: int


def normalize_comparison_text(value: str) -> str:
    """Normalize bounded role/location text without fuzzy semantic inference."""

    lowered = value.casefold().strip()
    collapsed_punctuation = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(collapsed_punctuation.split())


def hash_match_input(snapshot: MatchInputSnapshot) -> str:
    """Hash only the actual matching evidence and immutable Job requirements."""

    payload = snapshot.model_dump(mode="json")
    payload["match_policy_version"] = MATCH_POLICY_VERSION
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_analysis_key(*, input_hash: str, semantic_model: str | None) -> str:
    """Build the exact semantic-analysis identity used for cache and concurrency control."""

    value = "|".join(
        [
            input_hash,
            MATCH_POLICY_VERSION,
            SEMANTIC_PROMPT_VERSION,
            semantic_model or "deterministic",
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_semantic_evidence(snapshot: MatchInputSnapshot) -> list[SemanticEvidenceItem]:
    """Return explicit title evidence with stable IDs and bounded temporal context."""

    items: list[SemanticEvidenceItem] = []
    seen: set[tuple[str, str, str | None, bool | None]] = set()

    def add(
        title: str | None,
        source: Literal[
            "candidate_current_title",
            "professional_current_title",
            "employment_history",
        ],
        *,
        started_at: date | None = None,
        is_current: bool | None = None,
    ) -> None:
        if title is None:
            return
        normalized = normalize_comparison_text(title)
        started_value = str(started_at) if started_at is not None else None
        key = (normalized, source, started_value, is_current)
        if not normalized or key in seen:
            return
        seen.add(key)
        items.append(
            SemanticEvidenceItem(
                id=f"E{len(items) + 1}",
                title=title,
                source=source,
                started_at=started_at,
                is_current=is_current,
            )
        )

    add(snapshot.candidate_current_title, "candidate_current_title", is_current=True)
    if snapshot.professional_evidence is not None:
        add(
            snapshot.professional_evidence.current_title,
            "professional_current_title",
            is_current=True,
        )
        for experience in snapshot.professional_evidence.employment_history:
            add(
                experience.title,
                "employment_history",
                started_at=experience.started_at,
                is_current=experience.is_current,
            )
    return items


def build_deterministic_criteria(snapshot: MatchInputSnapshot) -> list[MatchCriterion]:
    """Build the full criterion set while keeping unsupported requirements explicitly unknown."""

    criteria: list[MatchCriterion] = []
    title_evidence = build_semantic_evidence(snapshot)
    approved_titles = [snapshot.job_title, *snapshot.alternate_titles]
    approved_normalized = {
        normalize_comparison_text(title) for title in approved_titles if title.strip()
    }
    canonical_current_title = next(
        (item for item in title_evidence if item.source == "candidate_current_title"),
        None,
    )
    provider_current_title = next(
        (item for item in title_evidence if item.source == "professional_current_title"),
        None,
    )
    current_title_evidence = canonical_current_title or provider_current_title
    exact_titles = (
        [current_title_evidence]
        if current_title_evidence is not None
        and normalize_comparison_text(current_title_evidence.title) in approved_normalized
        else []
    )
    if exact_titles:
        role = MatchCriterion(
            key="role_alignment",
            label="Role alignment",
            category="role",
            weight=2,
            status=MatchCriterionStatus.SUPPORTED,
            reason="Candidate title evidence exactly matches the approved role or alternate title.",
            evidence_ids=[item.id for item in exact_titles],
        )
    elif title_evidence:
        role = MatchCriterion(
            key="role_alignment",
            label="Role alignment",
            category="role",
            weight=2,
            status=MatchCriterionStatus.UNKNOWN,
            reason=(
                "Available titles do not exactly match; semantic role alignment is not yet known."
            ),
            evidence_ids=[],
        )
    else:
        role = MatchCriterion(
            key="role_alignment",
            label="Role alignment",
            category="role",
            weight=2,
            status=MatchCriterionStatus.UNKNOWN,
            reason="No title evidence is available for role alignment.",
            evidence_ids=[],
        )
    criteria.append(role)

    if snapshot.seniority:
        criteria.append(
            MatchCriterion(
                key="seniority",
                label="Seniority",
                category="seniority",
                weight=2,
                status=MatchCriterionStatus.UNKNOWN,
                reason=(
                    "Seniority requires evidence-grounded semantic classification from explicit "
                    "title history."
                ),
                evidence_ids=[],
            )
        )

    if snapshot.locations:
        provider_location = (
            snapshot.professional_evidence.location
            if snapshot.professional_evidence is not None
            else None
        )
        effective_location = snapshot.candidate_location or provider_location
        approved_locations = {
            normalize_comparison_text(location)
            for location in snapshot.locations
            if location.strip()
        }
        if (
            effective_location is not None
            and normalize_comparison_text(effective_location) in approved_locations
        ):
            status = MatchCriterionStatus.SUPPORTED
            reason = "Candidate location evidence exactly matches an approved Job location."
        elif effective_location is not None:
            status = MatchCriterionStatus.CONTRADICTED
            reason = "Known Candidate location evidence does not match an approved Job location."
        else:
            status = MatchCriterionStatus.UNKNOWN
            reason = "No Candidate location evidence is available."
        criteria.append(
            MatchCriterion(
                key="location",
                label="Location",
                category="location",
                weight=1,
                status=status,
                reason=reason,
                evidence_ids=[],
            )
        )

    if snapshot.min_years_experience is not None:
        criteria.append(
            MatchCriterion(
                key="minimum_experience",
                label=f"Minimum {snapshot.min_years_experience} years experience",
                category="experience",
                weight=2,
                status=MatchCriterionStatus.UNKNOWN,
                reason=(
                    "Current evidence does not contain complete employment end dates, so verified "
                    "total experience cannot be reconstructed."
                ),
                evidence_ids=[],
            )
        )

    for index, skill in enumerate(snapshot.required_skills):
        criteria.append(
            MatchCriterion(
                key=f"required_skill_{index + 1}",
                label=skill,
                category="required_skill",
                weight=2,
                status=MatchCriterionStatus.UNKNOWN,
                reason=(
                    "No verified Candidate skill evidence exists in the current evidence contract."
                ),
                evidence_ids=[],
            )
        )

    for index, skill in enumerate(snapshot.preferred_skills):
        criteria.append(
            MatchCriterion(
                key=f"preferred_skill_{index + 1}",
                label=skill,
                category="preferred_skill",
                weight=1,
                status=MatchCriterionStatus.UNKNOWN,
                reason=(
                    "No verified Candidate skill evidence exists in the current evidence contract."
                ),
                evidence_ids=[],
            )
        )

    if snapshot.employment_type is not None:
        criteria.append(
            MatchCriterion(
                key="employment_type",
                label=f"Employment type: {snapshot.employment_type.value}",
                category="employment_type",
                weight=1,
                status=MatchCriterionStatus.UNKNOWN,
                reason="Candidate employment-type preference is not available.",
                evidence_ids=[],
            )
        )

    if snapshot.work_arrangement is not None:
        criteria.append(
            MatchCriterion(
                key="work_arrangement",
                label=f"Work arrangement: {snapshot.work_arrangement.value}",
                category="work_arrangement",
                weight=1,
                status=MatchCriterionStatus.UNKNOWN,
                reason="Candidate work-arrangement preference is not available.",
                evidence_ids=[],
            )
        )

    return criteria


def semantic_analysis_is_useful(
    snapshot: MatchInputSnapshot,
    criteria: list[MatchCriterion],
) -> bool:
    """Return whether constrained semantic classification can improve current evidence truth."""

    evidence = build_semantic_evidence(snapshot)
    if not evidence:
        return False
    role = next(item for item in criteria if item.key == "role_alignment")
    if role.status is MatchCriterionStatus.UNKNOWN:
        return True
    return any(item.key == "seniority" for item in criteria)


def merge_semantic_output(
    criteria: list[MatchCriterion],
    output: SemanticMatchOutput,
    *,
    valid_evidence_ids: set[str],
) -> list[MatchCriterion]:
    """Apply validated semantic role/seniority verdicts without altering other criteria."""

    def validated(verdict: SemanticCriterionVerdict) -> SemanticCriterionVerdict:
        if any(evidence_id not in valid_evidence_ids for evidence_id in verdict.evidence_ids):
            raise ValueError("Semantic provider cited evidence that was not supplied")
        if verdict.status is not MatchCriterionStatus.UNKNOWN and not verdict.evidence_ids:
            raise ValueError("Semantic provider verdict must cite evidence")
        return verdict

    role_verdict = validated(output.role_alignment)
    seniority_verdict = validated(output.seniority_alignment)
    merged: list[MatchCriterion] = []
    for criterion in criteria:
        if criterion.key == "role_alignment" and criterion.status is MatchCriterionStatus.UNKNOWN:
            merged.append(
                criterion.model_copy(
                    update={
                        "status": role_verdict.status,
                        "reason": role_verdict.reason,
                        "evidence_ids": role_verdict.evidence_ids,
                    }
                )
            )
        elif criterion.key == "seniority":
            merged.append(
                criterion.model_copy(
                    update={
                        "status": seniority_verdict.status,
                        "reason": seniority_verdict.reason,
                        "evidence_ids": seniority_verdict.evidence_ids,
                    }
                )
            )
        else:
            merged.append(criterion)
    return merged


def calculate_score(criteria: list[MatchCriterion]) -> MatchScore:
    """Calculate evidence-backed match score and independent evidence coverage."""

    total_weight = sum(item.weight for item in criteria)
    if total_weight <= 0:
        return MatchScore(match_score=0, evidence_coverage=0)
    supported = sum(
        item.weight for item in criteria if item.status is MatchCriterionStatus.SUPPORTED
    )
    known = sum(
        item.weight for item in criteria if item.status is not MatchCriterionStatus.UNKNOWN
    )
    return MatchScore(
        match_score=(100 * supported) // total_weight,
        evidence_coverage=(100 * known) // total_weight,
    )
