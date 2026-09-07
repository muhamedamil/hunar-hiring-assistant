import type { ScreeningAnswerType } from "@/lib/jobs/types";

export type OutreachReadiness = "READY_FOR_EXECUTION" | "STALE";

export interface OutreachQuestionDraft {
  source_job_question_id: string | null;
  key: string;
  prompt: string;
  answer_type: ScreeningAnswerType;
  required: boolean;
  options: string[];
}

export interface OutreachQuestion extends OutreachQuestionDraft {
  id: string;
}

export interface OutreachPreparation {
  job_candidate_id: string;
  candidate_id: string;
  candidate_name: string;
  job_id: string;
  role: string;
  definition_version: number;
  masked_phone: string | null;
  default_screening_questions: OutreachQuestionDraft[];
  preparation_token: string;
  requested_action: "Voice screening outreach";
  can_prepare: boolean;
  blockers: string[];
}

export interface OutreachRequest {
  id: string;
  job_candidate_id: string;
  decision_match_id: string;
  candidate_name: string;
  candidate_location: string | null;
  masked_phone: string;
  screening_questions: OutreachQuestion[];
  screening_context_hash: string;
  requested_action: "Voice screening outreach";
  readiness: OutreachReadiness;
  stale_reasons: string[];
  created_at: string;
}

export interface OutreachListResponse {
  items: OutreachRequest[];
  limit: number;
  offset: number;
}

export interface PrepareOutreachInput {
  preparation_token: string;
  screening_questions: OutreachQuestionDraft[];
}
