import type { CandidateSummary } from "@/lib/candidates/types";

export type JobCandidateSource = "manual" | "sourcing";
export type ShortlistStatus = "reviewing" | "shortlisted" | "not_selected";
export type MatchStatus = "analyzing" | "completed" | "failed";
export type MatchAnalysisMode = "deterministic" | "hybrid_gemini" | "deterministic_fallback";
export type MatchCriterionStatus = "supported" | "contradicted" | "unknown";
export type CallReadiness = "ready" | "not_ready";

export interface MatchCriterion {
  key: string;
  label: string;
  category: string;
  weight: number;
  status: MatchCriterionStatus;
  reason: string;
  evidence_ids: string[];
}

export interface MatchEvaluation {
  id: string;
  job_candidate_id: string;
  definition_version: number;
  source_sourcing_result_id: string | null;
  source_sourcing_run_id: string | null;
  source_definition_version: number | null;
  source_evidence_version: string | null;
  candidate_revision: number;
  matcher_version: string;
  analysis_mode: MatchAnalysisMode;
  status: MatchStatus;
  semantic_model: string | null;
  semantic_prompt_version: string | null;
  semantic_failure_code: string | null;
  retry_after_seconds: number | null;
  match_score: number | null;
  evidence_coverage: number | null;
  match_reasons: MatchCriterion[];
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

export interface MatchFreshness {
  is_fresh: boolean;
  stale_reasons: string[];
}

export interface JobCandidateSummary {
  id: string;
  job_id: string;
  candidate: CandidateSummary;
  created_source: JobCandidateSource;
  preferred_sourcing_result_id: string | null;
  shortlist_status: ShortlistStatus;
  revision: number;
  current_match: MatchEvaluation | null;
  match_freshness: MatchFreshness;
  decision_is_current: boolean;
  call_readiness: CallReadiness;
  created_at: string;
  updated_at: string;
}

export interface JobCandidateDetail extends JobCandidateSummary {
  current_job_status: "draft" | "ready";
  current_job_definition_version: number | null;
  decision_match_id: string | null;
}

export interface JobCandidateListResponse {
  items: JobCandidateSummary[];
  limit: number;
  offset: number;
}

export interface MatchHistoryResponse {
  items: MatchEvaluation[];
  limit: number;
  offset: number;
}
