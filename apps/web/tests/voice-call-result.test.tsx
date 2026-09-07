import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { VoiceCallResultPanel } from "@/components/outreach/voice-call-result";
import { api } from "@/lib/api/client";
import type { VoiceCallResult } from "@/lib/call-results/types";
import type { OutreachQuestion } from "@/lib/outreach/types";
import type { VoiceCallExecution } from "@/lib/voice-calls/types";

vi.mock("@/lib/api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const question: OutreachQuestion = {
  id: "question-id",
  source_job_question_id: null,
  key: "interest",
  prompt: "Are you interested?",
  answer_type: "short_text",
  required: true,
  options: [],
};

function execution(status: VoiceCallExecution["status"], callId: string | null) {
  return {
    id: "execution-id",
    outreach_request_id: "outreach-id",
    status,
    language: "ENGLISH" as const,
    timezone: "Asia/Kolkata",
    agent_contract_version: "hunar_voice_screening_en_v1",
    provider_call_id: callId,
    provider_initial_status: null,
    failure_code: null,
    submitted_at: null,
    created_at: "2026-09-07T00:00:00Z",
    updated_at: "2026-09-07T00:00:00Z",
  };
}

function result(changes: Partial<VoiceCallResult> = {}): VoiceCallResult {
  return {
    id: "result-id",
    voice_call_execution_id: "execution-id",
    provider_call_id: "call-id",
    provider_status: "COMPLETED",
    lifecycle_status: "COMPLETED",
    answered_by: "HUMAN",
    screening_result_state: "available",
    result_failure_code: null,
    conversation_outcome: "completed",
    candidate_interest: "interested",
    notes: null,
    duration_seconds: 42,
    started_at: null,
    ended_at: null,
    recording_available: true,
    observed_at: "2026-09-07T00:00:00Z",
    updated_at: "2026-09-07T00:00:00Z",
    answers: [{
      outreach_question_id: "question-id",
      position: 1,
      answer_state: "answered",
      answer_text: "Yes",
    }],
    ...changes,
  };
}

function show(row: VoiceCallExecution) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    <VoiceCallResultPanel execution={row} questions={[question]} />
  </QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.post).mockResolvedValue({ state: "finalized", result: result() });
});

it("renders human results against immutable question IDs without a recording URL", async () => {
  vi.mocked(api.get).mockResolvedValue(result());
  show(execution("submitted", "call-id"));
  expect(await screen.findByText("Screening completed")).toBeInTheDocument();
  expect(screen.getByText("Are you interested?")).toBeInTheDocument();
  expect(screen.getByText("Yes")).toBeInTheDocument();
  expect(screen.getByText("Recording available")).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("https://");
});

it("renders machine completion with no accepted Candidate answers", async () => {
  vi.mocked(api.get).mockResolvedValue(result({
    answered_by: "MACHINE",
    screening_result_state: "unavailable",
    answers: [],
  }));
  show(execution("submitted", "call-id"));
  expect(await screen.findByText(/machine\/voicemail/)).toBeInTheDocument();
  expect(screen.queryByText("Yes")).not.toBeInTheDocument();
});

it("offers GET-only reconciliation only when UNKNOWN has a known call ID", async () => {
  vi.mocked(api.get).mockResolvedValue(null);
  show(execution("unknown", "call-id"));
  await userEvent.click(await screen.findByRole("button", { name: "Check Hunar safely" }));
  expect(api.post).toHaveBeenCalledWith(
    "/voice-call-executions/execution-id/screening-result/reconcile",
  );
});

it("does not offer reconciliation or resend for UNKNOWN without a call ID", async () => {
  vi.mocked(api.get).mockResolvedValue(null);
  show(execution("unknown", null));
  expect(await screen.findByText(/No safe provider call identity/)).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByText(/Do not resend/)).toBeInTheDocument();
});
