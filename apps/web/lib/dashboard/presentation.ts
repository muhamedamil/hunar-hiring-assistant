import type {
  DashboardAttentionKind,
  DashboardScreeningState,
  ScreeningAnswerState,
  VoiceCallSubmissionStatus,
} from "@/lib/dashboard/types";

export const screeningStateLabels: Record<DashboardScreeningState, string> = {
  queued: "Queued",
  awaiting_result: "Awaiting result",
  dispatch_failed: "Dispatch failed",
  submission_unknown: "Submission uncertain",
  result_available: "Result available",
  result_unavailable: "Result unavailable",
  result_invalid: "Result invalid",
};

export const attentionKindLabels: Record<DashboardAttentionKind, string> = {
  review_candidate: "Review candidate",
  dispatch_failed: "Dispatch failed",
  submission_unknown: "Submission uncertain",
  result_invalid: "Result invalid",
  result_unavailable: "Result unavailable",
};

export const submissionStatusLabels: Record<VoiceCallSubmissionStatus, string> = {
  queued: "Queued",
  submitted: "Submitted",
  failed: "Failed",
  unknown: "Unknown",
};

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function answerDisplay(
  state: ScreeningAnswerState | null,
  text: string | null,
): string {
  if (state === null) return "No authoritative answer recorded";
  if (state === "no_clear_answer") return "No clear answer";
  if (state === "not_asked") return "Not asked";
  return text ?? "No authoritative answer recorded";
}

export function isUnresolvedScreeningState(state: DashboardScreeningState): boolean {
  return state === "queued" || state === "awaiting_result" || state === "submission_unknown";
}
