import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OutreachList } from "@/components/outreach/outreach-list";
import { OutreachPreparation } from "@/components/outreach/outreach-preparation";
import * as outreachApi from "@/lib/outreach/api";

const push = vi.fn();
const relationId = "33333333-3333-4333-8333-333333333333";
const questionId = "44444444-4444-4444-8444-444444444444";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/outreach/api", () => ({
  getOutreachPreparation: vi.fn(),
  listOutreachRequests: vi.fn(),
  prepareOutreach: vi.fn(),
}));

function renderPreparation() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OutreachPreparation jobCandidateId={relationId} />
    </QueryClientProvider>,
  );
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OutreachList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(outreachApi.getOutreachPreparation).mockResolvedValue({
    job_candidate_id: relationId,
    candidate_id: "22222222-2222-4222-8222-222222222222",
    candidate_name: "Aisha Khan",
    job_id: "11111111-1111-4111-8111-111111111111",
    role: "Backend Engineer",
    definition_version: 2,
    masked_phone: "+91••••••3210",
    default_screening_questions: [
      {
        source_job_question_id: questionId,
        key: "interest",
        prompt: "Why are you interested in this role?",
        answer_type: "short_text",
        required: true,
        options: [],
      },
    ],
    preparation_token: "a".repeat(64),
    requested_action: "Voice screening outreach",
    can_prepare: true,
    blockers: [],
  });
  vi.mocked(outreachApi.prepareOutreach).mockResolvedValue({
    id: "55555555-5555-4555-8555-555555555555",
    job_candidate_id: relationId,
    decision_match_id: "66666666-6666-4666-8666-666666666666",
    candidate_name: "Aisha Khan",
    candidate_location: "Bengaluru",
    masked_phone: "+91••••••3210",
    screening_questions: [
      {
        id: "77777777-7777-4777-8777-777777777777",
        source_job_question_id: questionId,
        key: "interest",
        prompt: "Why are you interested in this role?",
        answer_type: "short_text",
        required: true,
        options: [],
      },
    ],
    screening_context_hash: "b".repeat(64),
    requested_action: "Voice screening outreach",
    readiness: "READY_FOR_EXECUTION",
    stale_reasons: [],
    created_at: "2026-09-06T10:00:00Z",
  });
  vi.mocked(outreachApi.listOutreachRequests).mockResolvedValue({
    items: [
      {
        id: "55555555-5555-4555-8555-555555555555",
        job_candidate_id: relationId,
        decision_match_id: "66666666-6666-4666-8666-666666666666",
        candidate_name: "Aisha Khan",
        candidate_location: "Bengaluru",
        masked_phone: "+91••••••3210",
        screening_questions: [],
        screening_context_hash: "b".repeat(64),
        requested_action: "Voice screening outreach",
        readiness: "READY_FOR_EXECUTION",
        stale_reasons: [],
        created_at: "2026-09-06T10:00:00Z",
      },
      {
        id: "88888888-8888-4888-8888-888888888888",
        job_candidate_id: "99999999-9999-4999-8999-999999999999",
        decision_match_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        candidate_name: "No Location Candidate",
        candidate_location: null,
        masked_phone: "+91••••••4567",
        screening_questions: [],
        screening_context_hash: "c".repeat(64),
        requested_action: "Voice screening outreach",
        readiness: "READY_FOR_EXECUTION",
        stale_reasons: [],
        created_at: "2026-09-06T09:00:00Z",
      },
    ],
    limit: 20,
    offset: 0,
  });
});

describe("OutreachPreparation", () => {
  it("reuses Job questions, preserves provenance, and strips client keys", async () => {
    renderPreparation();
    const user = userEvent.setup();

    expect(await screen.findByText("Aisha Khan")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Why are you interested in this role?")).toBeInTheDocument();
    expect(screen.getByText("Changes here apply only to this outreach.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm ready for execution" }));

    await waitFor(() => {
      expect(outreachApi.prepareOutreach).toHaveBeenCalledWith(relationId, {
        preparation_token: "a".repeat(64),
        screening_questions: [
          {
            source_job_question_id: questionId,
            key: "interest",
            prompt: "Why are you interested in this role?",
            answer_type: "short_text",
            required: true,
            options: [],
          },
        ],
      });
      expect(push).toHaveBeenCalledWith("/outreach/55555555-5555-4555-8555-555555555555");
    });
  });
});

describe("OutreachList", () => {
  it("shows Candidate names and only renders locations when available", async () => {
    renderList();

    expect(await screen.findByText("Aisha Khan")).toBeInTheDocument();
    expect(screen.getByText("Bengaluru")).toBeInTheDocument();
    expect(screen.getByText("No Location Candidate")).toBeInTheDocument();
    expect(screen.queryByText("Location unavailable")).not.toBeInTheDocument();
  });
});
