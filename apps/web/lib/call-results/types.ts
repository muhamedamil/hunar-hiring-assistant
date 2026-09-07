export type TerminalLifecycle = "COMPLETED" | "NOT_CONNECTED" | "FAILED" | "CANCELLED";
export type ScreeningResultState = "available" | "unavailable" | "invalid";
export type ScreeningAnswerState = "answered" | "no_clear_answer" | "not_asked";

export interface VoiceScreeningAnswer {
  outreach_question_id: string;
  position: number;
  answer_state: ScreeningAnswerState;
  answer_text: string | null;
}

export interface VoiceCallResult {
  id: string;
  voice_call_execution_id: string;
  provider_call_id: string;
  provider_status: TerminalLifecycle;
  lifecycle_status: TerminalLifecycle;
  answered_by: "HUMAN" | "MACHINE" | "UNKNOWN" | null;
  screening_result_state: ScreeningResultState;
  result_failure_code: string | null;
  conversation_outcome: string | null;
  candidate_interest: string | null;
  notes: string | null;
  duration_seconds: number | null;
  started_at: string | null;
  ended_at: string | null;
  recording_available: boolean;
  observed_at: string;
  updated_at: string;
  answers: VoiceScreeningAnswer[];
}

export interface ReconciliationResult {
  state: "already_finalized" | "not_terminal" | "finalized" | "enriched";
  result: VoiceCallResult | null;
}
