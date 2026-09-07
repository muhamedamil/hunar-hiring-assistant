import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardOverview } from "@/components/dashboard/dashboard-overview";
import * as dashboardApi from "@/lib/dashboard/api";
import type { DashboardOverview as DashboardOverviewData } from "@/lib/dashboard/types";

vi.mock("@/lib/dashboard/api", () => ({ getDashboardOverview: vi.fn() }));

function overview(changes: Partial<DashboardOverviewData> = {}): DashboardOverviewData {
  return {
    generated_at: "2026-09-08T00:00:00Z",
    jobs: { total: 12, draft: 2, ready: 10 },
    candidates: { total: 84 },
    pipeline: { reviewing: 4, shortlisted: 17, not_selected: 3 },
    screenings: {
      total: 9,
      queued: 1,
      awaiting_result: 1,
      dispatch_failed: 1,
      submission_unknown: 1,
      result_available: 3,
      result_unavailable: 1,
      result_invalid: 1,
      interested: 2,
    },
    needs_attention: [
      {
        kind: "submission_unknown",
        candidate_id: "candidate-1",
        candidate_name: "Aisha Khan",
        job_id: "job-1",
        job_candidate_id: "relation-1",
        job_title: "Backend Engineer",
        execution_id: "execution-1",
        outreach_request_id: "outreach-1",
        occurred_at: "2026-09-08T00:00:00Z",
      },
    ],
    recent_screenings: [
      {
        execution_id: "execution-2",
        outreach_request_id: "outreach-2",
        job_candidate_id: "relation-2",
        candidate_id: "candidate-2",
        candidate_name: "Rahul Menon",
        job_id: "job-2",
        job_title: "Data Engineer",
        job_definition_version: 1,
        screening_state: "awaiting_result",
        submission_status: "submitted",
        conversation_outcome: "partial",
        candidate_interest: null,
        duration_seconds: null,
        observed_at: null,
        sort_at: "2026-09-08T00:00:01Z",
      },
    ],
    ...changes,
  };
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardOverview />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(dashboardApi.getDashboardOverview).mockResolvedValue(overview());
});

describe("DashboardOverview", () => {
  it("renders authoritative metrics, attention, and unresolved recent screenings", async () => {
    const view = show();
    expect(await screen.findByText("Recruiting Overview")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("84")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Aisha Khan")).toBeInTheDocument();
    expect(screen.getByText("Submission uncertain")).toBeInTheDocument();
    expect(screen.getByText("Rahul Menon")).toBeInTheDocument();
    expect(screen.getByText("Awaiting result")).toBeInTheDocument();
    expect(screen.getByText("Partial")).toBeInTheDocument();
    expect(view.container.querySelector("time")?.getAttribute("datetime")).toBe(
      "2026-09-08T00:00:01Z",
    );
    expect(screen.queryByText(/Module \d/)).not.toBeInTheDocument();
  });

  it("uses result_available for the screening KPI rather than total call completion", async () => {
    show();
    await screen.findByText("Screening Results");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
  });

  it("renders explicit empty states without deriving totals from local rows", async () => {
    vi.mocked(dashboardApi.getDashboardOverview).mockResolvedValue(
      overview({
        jobs: { total: 0, draft: 0, ready: 0 },
        candidates: { total: 0 },
        pipeline: { reviewing: 0, shortlisted: 0, not_selected: 0 },
        screenings: {
          total: 0,
          queued: 0,
          awaiting_result: 0,
          dispatch_failed: 0,
          submission_unknown: 0,
          result_available: 0,
          result_unavailable: 0,
          result_invalid: 0,
          interested: 0,
        },
        needs_attention: [],
        recent_screenings: [],
      }),
    );
    show();
    expect(await screen.findByText("Nothing needs attention right now.")).toBeInTheDocument();
    expect(screen.getByText("No voice screenings yet.")).toBeInTheDocument();
  });
});
