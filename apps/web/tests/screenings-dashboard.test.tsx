import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScreeningDetail } from "@/components/dashboard/screening-detail";
import { ScreeningDetailContent } from "@/components/dashboard/screening-detail-content";
import { ScreeningsWorkspace } from "@/components/dashboard/screenings-workspace";
import { ApiError } from "@/lib/api/errors";
import * as dashboardApi from "@/lib/dashboard/api";
import type { DashboardScreeningDetail } from "@/lib/dashboard/types";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/dashboard/api", () => ({
  listDashboardScreenings: vi.fn(),
  getDashboardOverview: vi.fn(),
  getDashboardScreeningDetail: vi.fn(),
}));

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function detail(changes: Partial<DashboardScreeningDetail> = {}): DashboardScreeningDetail {
  return {
    execution_id: "execution-1",
    outreach_request_id: "outreach-1",
    job_candidate_id: "relation-1",
    candidate_id: "candidate-1",
    candidate_name: "Aisha Khan",
    job_id: "job-1",
    job_title: "Historical Backend Engineer",
    job_definition_version: 1,
    screening_state: "result_available",
    submission_status: "unknown",
    provider_status: "COMPLETED",
    lifecycle_status: "COMPLETED",
    answered_by: "HUMAN",
    conversation_outcome: "completed",
    candidate_interest: "interested",
    duration_seconds: 42,
    observed_at: "2026-09-08T00:00:00Z",
    recording_available: true,
    notes: "Candidate prefers mornings.",
    questions: [
      {
        question_id: "q1",
        position: 1,
        prompt: "Why this historical role?",
        answer_state: "answered",
        answer_text: "Strong fit",
      },
      {
        question_id: "q2",
        position: 2,
        prompt: "Notice period?",
        answer_state: "no_clear_answer",
        answer_text: null,
      },
      {
        question_id: "q3",
        position: 3,
        prompt: "Available weekends?",
        answer_state: "not_asked",
        answer_text: null,
      },
      {
        question_id: "q4",
        position: 4,
        prompt: "Relocation?",
        answer_state: null,
        answer_text: null,
      },
    ],
    ...changes,
  };
}

function renderScreeningDetail(executionId = "execution-1") {
  const queryClient = client();
  return render(
    <QueryClientProvider client={queryClient}>
      <ScreeningDetail executionId={executionId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(dashboardApi.listDashboardScreenings).mockResolvedValue({
    items: [
      {
        execution_id: "execution-1",
        outreach_request_id: "outreach-1",
        job_candidate_id: "relation-1",
        candidate_id: "candidate-1",
        candidate_name: "Aisha Khan",
        job_id: "job-1",
        job_title: "Backend Engineer",
        job_definition_version: 1,
        screening_state: "result_available",
        submission_status: "unknown",
        conversation_outcome: "completed",
        candidate_interest: "interested",
        duration_seconds: 42,
        observed_at: "2026-09-08T00:00:00Z",
        sort_at: "2026-09-08T00:00:00Z",
      },
    ],
    total: 25,
    limit: 20,
    offset: 0,
  });
  vi.mocked(dashboardApi.getDashboardScreeningDetail).mockResolvedValue(detail());
});

describe("ScreeningsWorkspace", () => {
  it("uses server filters and pagination without a capped Job dropdown", async () => {
    render(
      <QueryClientProvider client={client()}>
        <ScreeningsWorkspace />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Aisha Khan")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /job/i })).not.toBeInTheDocument();
    expect(screen.getByText("42 sec")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Search screenings"), "  Aisha  ");
    await user.selectOptions(screen.getByLabelText("Screening state"), "result_available");
    await user.selectOptions(screen.getByLabelText("Candidate interest"), "interested");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(dashboardApi.listDashboardScreenings).toHaveBeenCalledWith(
        expect.objectContaining({
          q: "Aisha",
          state: "result_available",
          interest: "interested",
          offset: 0,
          limit: 20,
        }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(dashboardApi.listDashboardScreenings).toHaveBeenCalledWith(
        expect.objectContaining({ offset: 20 }),
      ),
    );
  });
});

describe("ScreeningDetailContent", () => {
  it("renders historical Job/questions and preserves all answer absence states", () => {
    render(<ScreeningDetailContent detail={detail()} />);
    expect(screen.getByText("Historical Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText("Why this historical role?")).toBeInTheDocument();
    expect(screen.getByText("Strong fit")).toBeInTheDocument();
    expect(screen.getByText("No clear answer")).toBeInTheDocument();
    expect(screen.getByText("Not asked")).toBeInTheDocument();
    expect(screen.getByText("No authoritative answer recorded")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByText("Result available")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getByText("Recording available")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it.each(["MACHINE", "UNKNOWN"] as const)(
    "does not invent Candidate answers for %s",
    (answeredBy) => {
      const row = detail({
        answered_by: answeredBy,
        questions: [
          {
            question_id: "q1",
            position: 1,
            prompt: "Why this role?",
            answer_state: null,
            answer_text: null,
          },
        ],
      });
      render(<ScreeningDetailContent detail={row} />);
      expect(
        screen.getByText("No human screening answers are available for this call."),
      ).toBeInTheDocument();
      expect(screen.getByText("No authoritative answer recorded")).toBeInTheDocument();
      expect(screen.queryByText("Strong fit")).not.toBeInTheDocument();
    },
  );

  it("shows controlled invalid-result copy with no provider or retry action", () => {
    render(<ScreeningDetailContent detail={detail({ screening_state: "result_invalid", questions: [] })} />);
    expect(screen.getByText("Screening result could not be safely normalized.")).toBeInTheDocument();
    expect(screen.queryByText(/Hunar/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("ScreeningDetail", () => {
  it("renders the stable missing-execution 404 state", async () => {
    vi.mocked(dashboardApi.getDashboardScreeningDetail).mockRejectedValueOnce(
      new ApiError(404, "VOICE_CALL_EXECUTION_NOT_FOUND", "Execution not found"),
    );
    renderScreeningDetail("missing");
    expect(await screen.findByText("Screening execution was not found.")).toBeInTheDocument();
  });

  it("fails closed when immutable historical context is inconsistent", async () => {
    vi.mocked(dashboardApi.getDashboardScreeningDetail).mockRejectedValueOnce(
      new ApiError(
        409,
        "DASHBOARD_HISTORICAL_CONTEXT_INVALID",
        "Historical context is inconsistent",
      ),
    );
    renderScreeningDetail();
    expect(
      await screen.findByText(
        "Screening historical context is inconsistent and cannot be displayed safely.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/current Job/i)).not.toBeInTheDocument();
  });
});
