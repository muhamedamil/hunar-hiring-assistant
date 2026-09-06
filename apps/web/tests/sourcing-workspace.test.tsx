import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  JobSourcingWorkspace,
  SourcingRunWorkspace,
} from "@/components/sourcing/sourcing-workspace";
import { ApiError } from "@/lib/api/errors";
import * as sourcingApi from "@/lib/sourcing/api";
import type { Job } from "@/lib/jobs/types";
import * as matchingApi from "@/lib/matching/api";
import type { SourcingRun } from "@/lib/sourcing/types";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/matching/api", () => ({
  addSourcedJobCandidate: vi.fn(),
}));

vi.mock("@/lib/sourcing/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/sourcing/api")>(
    "@/lib/sourcing/api",
  );
  return {
    ...actual,
    startSourcingRun: vi.fn(),
    listSourcingRuns: vi.fn(),
    getSourcingRun: vi.fn(),
    retrySourcingRun: vi.fn(),
    enrichSourcingResult: vi.fn(),
  };
});

function renderWithClient(node: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function job(status: "draft" | "ready" = "ready"): Job {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Senior Backend Engineer",
    company_name: "Hunar.ai",
    description: "Build reliable backend services for a production AI hiring product.",
    requirements: {
      alternate_titles: ["Backend Engineer"],
      required_skills: ["Python", "FastAPI"],
      preferred_skills: [],
      locations: ["Bangalore"],
      min_years_experience: 5,
      seniority: ["senior", "lead"],
      employment_type: "full_time",
      work_arrangement: "hybrid",
    },
    screening_questions: [],
    status,
    revision: 3,
    approved_version: 2,
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:00Z",
  };
}

function run(): SourcingRun {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    job_id: job().id,
    definition_version: 2,
    provider: "apollo",
    status: "completed",
    result_limit: 10,
    result_count: 1,
    provider_total_matches: 20,
    failure_code: null,
    retry_after_seconds: null,
    created_at: "2026-09-06T00:00:00Z",
    completed_at: "2026-09-06T00:00:01Z",
    criteria: {
      titles: ["Senior Backend Engineer", "Backend Engineer"],
      locations: ["Bangalore"],
      seniorities: ["senior"],
      unmapped_requirements: [
        { field: "required_skills", values: ["Python", "FastAPI"] },
        { field: "seniority", values: ["lead"] },
      ],
      result_limit: 10,
    },
    provider_query: {
      person_titles: ["Senior Backend Engineer", "Backend Engineer"],
      person_locations: ["Bangalore"],
      person_seniorities: ["senior"],
      include_similar_titles: false,
      page: 1,
      per_page: 10,
    },
    mapping_version: "apollo_people_search_v1",
    attempt_count: 1,
    started_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:01Z",
    results: [
      {
        id: "33333333-3333-4333-8333-333333333333",
        sourcing_run_id: "22222222-2222-4222-8222-222222222222",
        provider_person_id: "apollo-person-1",
        result_position: 1,
        first_name: "Sarah",
        last_name_obfuscated: "Ah***d",
        current_title: "Backend Engineer",
        organization_name: "Acme",
        email_available: true,
        phone_availability: "available",
        enrichment_priority: "possible",
        enrichment_priority_reasons: [
          {
            code: "alternate_title_exact",
            outcome: "positive",
            detail: "Exact alternate target title",
          },
          {
            code: "phone_available",
            outcome: "positive",
            detail: "Phone likely available",
          },
        ],
        enrichment_priority_algorithm_version: "search_evidence_priority_v1",
        candidate_id: null,
        created_at: "2026-09-06T00:00:01Z",
      },
    ],
    enrichments: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(sourcingApi.listSourcingRuns).mockResolvedValue({ items: [] });
});

describe("Module 3 sourcing UI", () => {
  it("blocks new search for DRAFT jobs while leaving history reachable", async () => {
    renderWithClient(<JobSourcingWorkspace job={job("draft")} />);

    expect(
      screen.getByText(/People search is unavailable while this Job is DRAFT/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Find people" })).not.toBeInTheDocument();
    expect(await screen.findByText("No sourcing runs yet.")).toBeInTheDocument();
  });

  it("starts a READY search with the bounded recruiter-selected result limit", async () => {
    const completed = run();
    vi.mocked(sourcingApi.startSourcingRun).mockResolvedValue(completed);
    renderWithClient(<JobSourcingWorkspace job={job("ready")} />);

    fireEvent.change(screen.getByLabelText("Results"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Find people" }));

    await waitFor(() => {
      expect(sourcingApi.startSourcingRun).toHaveBeenCalledWith(job().id, 10);
    });
    expect(push).toHaveBeenCalledWith(`/sourcing/${completed.id}`);
  });

  it("navigates to the persisted run when a provider search fails after run creation", async () => {
    vi.mocked(sourcingApi.startSourcingRun).mockRejectedValue(
      new ApiError(503, "APOLLO_SEARCH_UNAVAILABLE", "Apollo unavailable.", "request-1", {
        run_id: "66666666-6666-4666-8666-666666666666",
      }),
    );
    renderWithClient(<JobSourcingWorkspace job={job("ready")} />);

    fireEvent.click(screen.getByRole("button", { name: "Find people" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(
        "/sourcing/66666666-6666-4666-8666-666666666666",
      );
    });
  });

  it("renders backend-persisted mapped and unmapped criteria without match scores", async () => {
    vi.mocked(sourcingApi.getSourcingRun).mockResolvedValue(run());
    renderWithClient(<SourcingRunWorkspace runId={run().id} />);

    expect(await screen.findByText("Search criteria actually used")).toBeInTheDocument();
    expect(screen.getByText("Senior Backend Engineer, Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText(/required_skills: Python, FastAPI/)).toBeInTheDocument();
    expect(screen.getByText(/seniority: lead/)).toBeInTheDocument();
    expect(screen.getByText("Sarah Ah***d")).toBeInTheDocument();
    expect(screen.getByText("Possible")).toBeInTheDocument();
    expect(screen.getByText("Exact alternate target title")).toBeInTheDocument();
    expect(screen.getByText("Phone likely available")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Apollo search evidence only. Matching and shortlisting happen in a later module.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/92%|match score/i)).not.toBeInTheDocument();
  });

  it("enriches only after explicit recruiter action", async () => {
    const current = run();
    vi.mocked(sourcingApi.getSourcingRun).mockResolvedValue(current);
    vi.mocked(sourcingApi.enrichSourcingResult).mockResolvedValue({
      id: "44444444-4444-4444-8444-444444444444",
      sourcing_result_id: current.results[0].id,
      provider: "apollo",
      status: "pending",
      candidate_id: null,
      provider_request_id: null,
      credits_consumed: null,
      failure_code: null,
      retry_after_seconds: null,
      requested_at: null,
      completed_at: null,
      created_at: "2026-09-06T00:00:02Z",
      updated_at: "2026-09-06T00:00:02Z",
    });
    renderWithClient(<SourcingRunWorkspace runId={current.id} />);

    const button = await screen.findByRole("button", { name: "Enrich contact" });
    expect(sourcingApi.enrichSourcingResult).not.toHaveBeenCalled();
    fireEvent.click(button);

    await waitFor(() => {
      expect(sourcingApi.enrichSourcingResult).toHaveBeenCalledWith(current.results[0].id);
    });
  });

  it("keeps low-priority provider results visible and available for explicit enrichment", async () => {
    const current = run();
    current.result_count = 2;
    current.results.push({
      ...current.results[0],
      id: "77777777-7777-4777-8777-777777777777",
      provider_person_id: "apollo-person-2",
      result_position: 2,
      first_name: "Jordan",
      last_name_obfuscated: "Sm***h",
      current_title: "Account Executive",
      phone_availability: "available",
      enrichment_priority: "low_priority",
      enrichment_priority_reasons: [
        {
          code: "title_not_aligned",
          outcome: "negative",
          detail: "Current title does not exactly align with target titles",
        },
        {
          code: "phone_available",
          outcome: "positive",
          detail: "Phone likely available",
        },
      ],
    });
    vi.mocked(sourcingApi.getSourcingRun).mockResolvedValue(current);
    renderWithClient(<SourcingRunWorkspace runId={current.id} />);

    expect(await screen.findByText("Sarah Ah***d")).toBeInTheDocument();
    expect(screen.getByText("Jordan Sm***h")).toBeInTheDocument();
    expect(screen.getByText("Low priority")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Enrich contact" })).toHaveLength(2);
  });

  it("surfaces failed enrichment without offering a second credit-consuming action", async () => {
    const current = run();
    current.enrichments = [
      {
        id: "55555555-5555-4555-8555-555555555555",
        sourcing_result_id: current.results[0].id,
        provider: "apollo",
        status: "failed",
        candidate_id: null,
        provider_request_id: null,
        credits_consumed: null,
        failure_code: "APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED",
        retry_after_seconds: null,
        requested_at: "2026-09-06T00:00:02Z",
        completed_at: "2026-09-06T00:00:03Z",
        created_at: "2026-09-06T00:00:02Z",
        updated_at: "2026-09-06T00:00:03Z",
      },
    ];
    vi.mocked(sourcingApi.getSourcingRun).mockResolvedValue(current);
    renderWithClient(<SourcingRunWorkspace runId={current.id} />);

    expect(
      await screen.findByText(/APOLLO_ENRICHMENT_ATTEMPTS_EXHAUSTED/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enrich contact" }),
    ).not.toBeInTheDocument();
  });

  it("Review match attaches/evaluates the resolved Candidate and navigates to review", async () => {
    const current = run();
    const candidateId = "88888888-8888-4888-8888-888888888888";
    const relationId = "99999999-9999-4999-8999-999999999999";
    current.enrichments = [
      {
        id: "55555555-5555-4555-8555-555555555555",
        sourcing_result_id: current.results[0].id,
        provider: "apollo",
        status: "completed",
        candidate_id: candidateId,
        provider_request_id: null,
        credits_consumed: 1,
        failure_code: null,
        retry_after_seconds: null,
        requested_at: "2026-09-06T00:00:02Z",
        completed_at: "2026-09-06T00:00:03Z",
        created_at: "2026-09-06T00:00:02Z",
        updated_at: "2026-09-06T00:00:03Z",
      },
    ];
    vi.mocked(sourcingApi.getSourcingRun).mockResolvedValue(current);
    vi.mocked(matchingApi.addSourcedJobCandidate).mockResolvedValue({
      id: relationId,
      job_id: current.job_id,
    } as Awaited<ReturnType<typeof matchingApi.addSourcedJobCandidate>>);
    renderWithClient(<SourcingRunWorkspace runId={current.id} />);

    fireEvent.click(await screen.findByRole("button", { name: "Review match" }));

    await waitFor(() => {
      expect(matchingApi.addSourcedJobCandidate).toHaveBeenCalledWith(current.results[0].id);
      expect(push).toHaveBeenCalledWith(`/job-candidates/${relationId}`);
    });
  });

});
