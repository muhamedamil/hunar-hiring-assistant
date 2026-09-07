import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { VoiceCallResultPanel } from "@/components/outreach/voice-call-result";
import * as dashboardApi from "@/lib/dashboard/api";
import type { DashboardScreeningDetail } from "@/lib/dashboard/types";
import type { VoiceCallExecution } from "@/lib/voice-calls/types";

vi.mock("@/lib/dashboard/api", () => ({ getDashboardScreeningDetail: vi.fn() }));

const execution: VoiceCallExecution = {
  id: "execution-id", outreach_request_id: "outreach-id", status: "unknown", language: "ENGLISH",
  timezone: "Asia/Kolkata", agent_contract_version: "hunar_voice_screening_en_v1", provider_call_id: null,
  provider_initial_status: null, failure_code: null, submitted_at: null,
  created_at: "2026-09-07T00:00:00Z", updated_at: "2026-09-07T00:00:00Z",
};

function result(changes: Partial<DashboardScreeningDetail> = {}): DashboardScreeningDetail {
  return {
    execution_id: "execution-id", outreach_request_id: "outreach-id", job_candidate_id: "relation-id",
    candidate_id: "candidate-id", candidate_name: "Aisha Khan", job_id: "job-id", job_title: "Backend Engineer",
    job_definition_version: 1, screening_state: "result_available", submission_status: "unknown",
    provider_status: "COMPLETED", lifecycle_status: "COMPLETED", answered_by: "HUMAN",
    conversation_outcome: "completed", candidate_interest: "interested", duration_seconds: 42,
    observed_at: "2026-09-07T00:00:00Z", recording_available: true, notes: null,
    questions: [{ question_id: "question-id", position: 1, prompt: "Are you interested?", answer_state: "answered", answer_text: "Yes" }],
    ...changes,
  };
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><VoiceCallResultPanel execution={execution} /></QueryClientProvider>);
}

beforeEach(() => { vi.clearAllMocks(); vi.mocked(dashboardApi.getDashboardScreeningDetail).mockResolvedValue(result()); });

it("renders the same safe result projection used by Screening Detail", async () => {
  show();
  expect(await screen.findByText("Call Status")).toBeInTheDocument();
  expect(screen.getByText("Unknown")).toBeInTheDocument();
  expect(screen.getByText("Result available")).toBeInTheDocument();
  expect(screen.getByText("Are you interested?")).toBeInTheDocument();
  expect(within(screen.getByRole("list")).getByText("Yes")).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("https://");
  expect(screen.queryByText(/provider_call_id/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Hunar/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("invalidates Outreach reads once a terminal result projection arrives", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><VoiceCallResultPanel execution={execution} /></QueryClientProvider>);
  await screen.findByText("Result available");
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["outreach"] }));
});

it("keeps MACHINE results answer-safe", async () => {
  vi.mocked(dashboardApi.getDashboardScreeningDetail).mockResolvedValue(result({ answered_by: "MACHINE", questions: [{ question_id: "question-id", position: 1, prompt: "Are you interested?", answer_state: null, answer_text: null }] }));
  show();
  expect(await screen.findByText("No human screening answers are available for this call.")).toBeInTheDocument();
  expect(screen.getByText("No authoritative answer recorded")).toBeInTheDocument();
  expect(within(screen.getByRole("list")).queryByText("Yes")).not.toBeInTheDocument();
});
