import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { JobEditor } from "@/components/jobs/job-editor";
import { ApiError } from "@/lib/api/errors";
import * as jobsApi from "@/lib/jobs/api";
import type { Job } from "@/lib/jobs/types";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/jobs/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/jobs/api")>("@/lib/jobs/api");
  return {
    ...actual,
    analyzeJob: vi.fn(),
    createJob: vi.fn(),
    saveJobDraft: vi.fn(),
    markJobReady: vi.fn(),
    reopenJob: vi.fn(),
  };
});

function renderEditor(initialJob?: Job) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <JobEditor initialJob={initialJob} />
    </QueryClientProvider>,
  );
}

function readyJob(): Job {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    title: "Senior Python Engineer",
    company_name: "Hunar.ai",
    description: "Build reliable Python APIs for an AI hiring product.",
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
    screening_questions: [
      {
        id: "22222222-2222-4222-8222-222222222222",
        key: "interest",
        prompt: "Are you interested in this role?",
        answer_type: "yes_no",
        required: true,
        options: [],
      },
    ],
    status: "ready",
    revision: 1,
    approved_version: 1,
    created_at: "2026-09-05T10:00:00Z",
    updated_at: "2026-09-05T10:00:00Z",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("JobEditor", () => {
  it("keeps AI analysis non-authoritative and only fills editable suggestions", async () => {
    vi.mocked(jobsApi.analyzeJob).mockResolvedValue({
      suggested_title: "Senior Python Engineer",
      requirements: {
        alternate_titles: ["Backend Engineer"],
        required_skills: ["Python", "FastAPI"],
        preferred_skills: ["AWS"],
        locations: ["Bangalore"],
        min_years_experience: 5,
        seniority: ["senior"],
        employment_type: "full_time",
        work_arrangement: "hybrid",
      },
      suggested_screening_questions: [
        {
          key: "python_experience",
          prompt: "How many years of Python experience do you have?",
          answer_type: "number",
          required: true,
          options: [],
        },
      ],
    });

    renderEditor();
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText("Job description"),
      "Build reliable Python and FastAPI services for an AI hiring product.",
    );
    await user.click(screen.getByRole("button", { name: "Analyze with AI" }));

    await screen.findByText("AI suggestions added. Review them before saving or marking the job ready.");
    expect(screen.getByLabelText("Job title")).toHaveValue("Senior Python Engineer");
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByDisplayValue("How many years of Python experience do you have?")).toBeInTheDocument();
    expect(jobsApi.createJob).not.toHaveBeenCalled();
  });

  it("keeps manual editing available when AI analysis fails", async () => {
    vi.mocked(jobsApi.analyzeJob).mockRejectedValue(
      new ApiError(503, "JOB_ANALYSIS_UNAVAILABLE", "AI job analysis is temporarily unavailable."),
    );

    renderEditor();
    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText("Job description"),
      "Build reliable Python and FastAPI services for an AI hiring product.",
    );
    await user.click(screen.getByRole("button", { name: "Analyze with AI" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Manual editing is still available");
    expect(screen.getByLabelText("Job title")).not.toBeDisabled();
  });

  it("does not claim suggestions were added for an empty AI proposal", async () => {
    vi.mocked(jobsApi.analyzeJob).mockResolvedValue({
      suggested_title: "Senior Python Engineer",
      requirements: {
        alternate_titles: [],
        required_skills: [],
        preferred_skills: [],
        locations: [],
        min_years_experience: null,
        seniority: [],
        employment_type: null,
        work_arrangement: null,
      },
      suggested_screening_questions: [],
    });

    renderEditor();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Job title"), "Senior Python Engineer");
    await user.type(
      screen.getByLabelText("Job description"),
      "Build reliable Python and FastAPI services for an AI hiring product.",
    );
    await user.click(screen.getByRole("button", { name: "Analyze with AI" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "AI analysis completed but returned no usable requirements or screening questions.",
    );
    expect(screen.queryByText(/AI suggestions added/)).not.toBeInTheDocument();
  });

  it("requires a valid screening question before marking a new job ready", async () => {
    renderEditor();
    fireEvent.change(screen.getByLabelText("Job title"), { target: { value: "Engineer" } });
    fireEvent.change(screen.getByLabelText("Job description"), {
      target: { value: "A sufficiently detailed Job Description for this role." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mark ready" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Add at least one screening question before marking the job ready.",
    );
    expect(jobsApi.createJob).not.toHaveBeenCalled();
  });

  it("reopens a READY job before permitting definition edits", async () => {
    const current = readyJob();
    vi.mocked(jobsApi.reopenJob).mockResolvedValue({
      ...current,
      status: "draft",
      revision: 2,
    });

    renderEditor(current);
    expect(screen.getByLabelText("Job title")).toBeDisabled();
    expect(screen.getByRole("link", { name: "Find people" })).toHaveAttribute(
      "href",
      `/jobs/${current.id}/sourcing`,
    );
    expect(screen.getByRole("link", { name: "Review candidates" })).toHaveAttribute(
      "href",
      `/jobs/${current.id}/candidates`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reopen to edit" }));
    await waitFor(() => expect(screen.getByLabelText("Job title")).not.toBeDisabled());
    expect(jobsApi.reopenJob).toHaveBeenCalledWith(current.id, current.revision);
  });
});
