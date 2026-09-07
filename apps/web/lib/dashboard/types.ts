export type DashboardScreeningState =
  | "queued"
  | "awaiting_result"
  | "dispatch_failed"
  | "submission_unknown"
  | "result_available"
  | "result_unavailable"
  | "result_invalid";

export type VoiceCallSubmissionStatus = "queued" | "submitted" | "failed" | "unknown";
export type CandidateInterest = "interested" | "not_interested" | "unclear";
export type ConversationOutcome =
  | "completed"
  | "partial"
  | "not_interested"
  | "wrong_person"
  | "not_available"
  | "disconnected"
  | "other";
export type ScreeningAnswerState = "answered" | "no_clear_answer" | "not_asked";
export type AnsweredBy = "HUMAN" | "MACHINE" | "UNKNOWN";
export type LifecycleStatus = "NOT_STARTED" | "IN_PROGRESS" | "NOT_CONNECTED" | "COMPLETED" | "FAILED" | "CANCELLED";
export type ProviderStatus = "NOT_STARTED" | "SCHEDULED" | "INITIATED" | "RINGING" | "IN_PROGRESS" | "COMPLETED" | "NOT_CONNECTED" | "CANCELLED" | "FAILED";

export type DashboardAttentionKind =
  | "review_candidate"
  | "dispatch_failed"
  | "submission_unknown"
  | "result_invalid"
  | "result_unavailable";

export interface DashboardJobMetrics { total: number; draft: number; ready: number }
export interface DashboardCandidateMetrics { total: number }
export interface DashboardPipelineMetrics { reviewing: number; shortlisted: number; not_selected: number }
export interface DashboardScreeningMetrics {
  total: number;
  queued: number;
  awaiting_result: number;
  dispatch_failed: number;
  submission_unknown: number;
  result_available: number;
  result_unavailable: number;
  result_invalid: number;
  interested: number;
}

export interface DashboardAttentionItem {
  kind: DashboardAttentionKind;
  candidate_id: string;
  candidate_name: string;
  job_id: string;
  job_candidate_id: string;
  job_title: string;
  execution_id: string | null;
  outreach_request_id: string | null;
  occurred_at: string;
}

export interface DashboardScreeningSummary {
  execution_id: string;
  outreach_request_id: string;
  job_candidate_id: string;
  candidate_id: string;
  candidate_name: string;
  job_id: string;
  job_title: string;
  job_definition_version: number;
  screening_state: DashboardScreeningState;
  submission_status: VoiceCallSubmissionStatus;
  conversation_outcome: ConversationOutcome | null;
  candidate_interest: CandidateInterest | null;
  duration_seconds: number | null;
  observed_at: string | null;
  sort_at: string;
}

export interface DashboardScreeningListResponse {
  items: DashboardScreeningSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DashboardQuestionAnswer {
  question_id: string;
  position: number;
  prompt: string;
  answer_state: ScreeningAnswerState | null;
  answer_text: string | null;
}

export interface DashboardScreeningDetail extends Omit<DashboardScreeningSummary, "sort_at"> {
  provider_status: ProviderStatus | null;
  lifecycle_status: LifecycleStatus | null;
  answered_by: AnsweredBy | null;
  recording_available: boolean;
  notes: string | null;
  questions: DashboardQuestionAnswer[];
}

export interface DashboardOverview {
  generated_at: string;
  jobs: DashboardJobMetrics;
  candidates: DashboardCandidateMetrics;
  pipeline: DashboardPipelineMetrics;
  screenings: DashboardScreeningMetrics;
  needs_attention: DashboardAttentionItem[];
  recent_screenings: DashboardScreeningSummary[];
}

export interface DashboardScreeningFilters {
  jobId?: string;
  state?: DashboardScreeningState;
  interest?: CandidateInterest;
  q?: string;
  limit?: number;
  offset?: number;
}
