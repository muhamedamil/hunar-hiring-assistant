import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { JobCandidateDetail } from "@/components/matching/job-candidate-detail";
import * as matchingApi from "@/lib/matching/api";
import type { JobCandidateDetail as JobCandidateDetailType } from "@/lib/matching/types";

vi.mock("@/lib/matching/api", () => ({
  getJobCandidate: vi.fn(),
  listJobCandidateMatches: vi.fn(),
  evaluateJobCandidate: vi.fn(),
  updateShortlist: vi.fn(),
}));

const relationId = "33333333-3333-4333-8333-333333333333";

function detail(): JobCandidateDetailType {
  return {
    id: relationId,
    job_id: "11111111-1111-4111-8111-111111111111",
    candidate: {
      id: "22222222-2222-4222-8222-222222222222",
      full_name: "Candidate Example",
      current_title: "Backend Engineer",
      current_company: "Example Co",
      location: "Bangalore",
      has_email: true,
      has_phone: true,
      revision: 3,
      updated_at: "2026-09-06T10:00:00Z",
    },
    created_source: "sourcing",
    preferred_sourcing_result_id: "44444444-4444-4444-8444-444444444444",
    shortlist_status: "reviewing",
    revision: 4,
    current_match: {
      id: "55555555-5555-4555-8555-555555555555",
      job_candidate_id: relationId,
      definition_version: 2,
      source_sourcing_result_id: "44444444-4444-4444-8444-444444444444",
      source_sourcing_run_id: "66666666-6666-4666-8666-666666666666",
      source_definition_version: 1,
      source_evidence_version: "apollo_professional_evidence_v1",
      candidate_revision: 3,
      matcher_version: "candidate_job_match_v1",
      analysis_mode: "hybrid_gemini",
      status: "completed",
      semantic_model: "gemini-test",
      semantic_prompt_version: "candidate_match_semantic_v1",
      semantic_failure_code: null,
      retry_after_seconds: null,
      match_score: 40,
      evidence_coverage: 60,
      match_reasons: [
        {
          key: "role_alignment",
          label: "Role alignment",
          category: "role",
          weight: 2,
          status: "supported",
          reason: "Explicit title evidence supports role alignment.",
          evidence_ids: ["E1"],
        },
        {
          key: "required_skill_1",
          label: "Python",
          category: "required_skill",
          weight: 2,
          status: "unknown",
          reason: "No verified Candidate skill evidence exists in the current evidence contract.",
          evidence_ids: [],
        },
      ],
      started_at: "2026-09-06T10:00:00Z",
      completed_at: "2026-09-06T10:00:01Z",
      created_at: "2026-09-06T10:00:00Z",
    },
    match_freshness: { is_fresh: true, stale_reasons: [] },
    decision_is_current: false,
    call_readiness: "ready",
    created_at: "2026-09-06T10:00:00Z",
    updated_at: "2026-09-06T10:00:00Z",
    current_job_status: "ready",
    current_job_definition_version: 2,
    decision_match_id: null,
  };
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <JobCandidateDetail jobCandidateId={relationId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(matchingApi.getJobCandidate).mockResolvedValue(detail());
  vi.mocked(matchingApi.listJobCandidateMatches).mockResolvedValue({
    items: [detail().current_match!],
    limit: 20,
    offset: 0,
  });
});

describe("JobCandidateDetail", () => {
  it("shows fit evidence separately from call readiness and keeps unsupported skills unknown", async () => {
    renderDetail();

    expect(await screen.findByText("Candidate Example")).toBeInTheDocument();
    expect(screen.getByText("Match 40%")).toBeInTheDocument();
    expect(screen.getByText("Coverage 60%")).toBeInTheDocument();
    expect(screen.getByText("Call ready")).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh match" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze match" })).not.toBeInTheDocument();
  });

  it("requires an explicit recruiter shortlist action", async () => {
    vi.mocked(matchingApi.updateShortlist).mockResolvedValue({
      ...detail(),
      shortlist_status: "shortlisted",
      decision_is_current: true,
      decision_match_id: detail().current_match!.id,
      revision: 5,
    });
    renderDetail();
    const user = userEvent.setup();

    await screen.findByText("Candidate Example");
    await user.click(screen.getByRole("button", { name: "Shortlist" }));

    expect(matchingApi.updateShortlist).toHaveBeenCalledWith(relationId, 4, "shortlisted");
  });
});

it("shows an explicit retry recovery state when the initial assessment is unavailable", async () => {
  vi.mocked(matchingApi.getJobCandidate).mockResolvedValue({
    ...detail(),
    current_match: null,
    match_freshness: { is_fresh: false, stale_reasons: ["match_missing"] },
  });
  vi.mocked(matchingApi.listJobCandidateMatches).mockResolvedValue({
    items: [],
    limit: 20,
    offset: 0,
  });

  renderDetail();

  expect(await screen.findByText("Initial assessment unavailable")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry analysis" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analyze match" })).not.toBeInTheDocument();
});

it("surfaces an older recruiter decision after a fresh rematch", async () => {
  vi.mocked(matchingApi.getJobCandidate).mockResolvedValue({
    ...detail(),
    shortlist_status: "shortlisted",
    decision_is_current: false,
    decision_match_id: "77777777-7777-4777-8777-777777777777",
  });

  renderDetail();

  expect(
    await screen.findByText(/previous recruiter decision was made against an older match/i),
  ).toBeInTheDocument();
});

it("keeps shortlist workflow read-only while the Job is DRAFT", async () => {
  vi.mocked(matchingApi.getJobCandidate).mockResolvedValue({
    ...detail(),
    shortlist_status: "shortlisted",
    decision_is_current: true,
    decision_match_id: detail().current_match!.id,
    current_job_status: "draft",
    current_job_definition_version: null,
  });

  renderDetail();

  expect(await screen.findByRole("button", { name: "Back to reviewing" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Shortlist" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Not selected" })).toBeDisabled();
});
