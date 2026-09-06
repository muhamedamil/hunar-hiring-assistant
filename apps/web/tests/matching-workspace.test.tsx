import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { JobCandidateWorkspace } from "@/components/matching/job-candidate-workspace";
import * as candidatesApi from "@/lib/candidates/api";
import type { Job } from "@/lib/jobs/types";
import * as matchingApi from "@/lib/matching/api";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/candidates/api", () => ({ listCandidates: vi.fn() }));
vi.mock("@/lib/matching/api", () => ({
  listJobCandidates: vi.fn(),
  addManualJobCandidate: vi.fn(),
}));

function job(): Job {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Senior Backend Engineer",
    company_name: "Hunar",
    description: "Build reliable backend systems for the hiring assistant assessment.",
    requirements: {
      alternate_titles: ["Backend Engineer"],
      required_skills: ["Python"],
      preferred_skills: [],
      locations: ["Bangalore"],
      min_years_experience: 5,
      seniority: ["senior"],
      employment_type: "full_time",
      work_arrangement: "hybrid",
    },
    screening_questions: [],
    status: "ready",
    revision: 1,
    approved_version: 2,
    created_at: "2026-09-06T10:00:00Z",
    updated_at: "2026-09-06T10:00:00Z",
  };
}

const candidate = {
  id: "22222222-2222-4222-8222-222222222222",
  full_name: "Candidate Example",
  current_title: "Backend Engineer",
  current_company: "Example Co",
  location: "Bangalore",
  has_email: true,
  has_phone: true,
  revision: 3,
  updated_at: "2026-09-06T10:00:00Z",
};

function renderWorkspace() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <JobCandidateWorkspace job={job()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(candidatesApi.listCandidates).mockResolvedValue({
    items: [candidate],
    limit: 100,
    offset: 0,
  });
  vi.mocked(matchingApi.listJobCandidates).mockResolvedValue({
    items: [],
    limit: 100,
    offset: 0,
  });
});

describe("JobCandidateWorkspace", () => {
  it("uses Candidate Core for Task-1 attachment and navigates directly to review", async () => {
    vi.mocked(matchingApi.addManualJobCandidate).mockResolvedValue({
      id: "33333333-3333-4333-8333-333333333333",
      job_id: job().id,
      candidate,
      created_source: "manual",
      preferred_sourcing_result_id: null,
      shortlist_status: "reviewing",
      revision: 0,
      current_match: null,
      match_freshness: { is_fresh: false, stale_reasons: ["match_missing"] },
      decision_is_current: false,
      call_readiness: "ready",
      created_at: "2026-09-06T10:00:00Z",
      updated_at: "2026-09-06T10:00:00Z",
      current_job_status: "ready",
      current_job_definition_version: 2,
      decision_match_id: null,
    });

    renderWorkspace();
    const user = userEvent.setup();

    expect(await screen.findByText("Candidate Example")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to job" }));

    await waitFor(() => {
      expect(matchingApi.addManualJobCandidate).toHaveBeenCalledWith(job().id, candidate.id);
      expect(push).toHaveBeenCalledWith(
        "/job-candidates/33333333-3333-4333-8333-333333333333",
      );
    });
  });
});
