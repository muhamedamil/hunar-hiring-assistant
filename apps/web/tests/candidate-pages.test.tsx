import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CandidateDetailPage from "@/app/candidates/[candidateId]/page";
import CandidatesPage from "@/app/candidates/page";
import * as candidatesApi from "@/lib/candidates/api";
import type { Candidate, CandidateListResponse } from "@/lib/candidates/types";

const replace = vi.fn();
const candidateId = "11111111-1111-4111-8111-111111111111";

vi.mock("next/navigation", () => ({
  useParams: () => ({ candidateId }),
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/candidates/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/candidates/api")>(
    "@/lib/candidates/api",
  );
  return {
    ...actual,
    getCandidate: vi.fn(),
    listCandidates: vi.fn(),
  };
});

function renderWithQueryClient(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

function candidate(): Candidate {
  return {
    id: candidateId,
    full_name: "Sarah Ahmed",
    current_title: "Backend Engineer",
    current_company: "Acme",
    location: "Bangalore",
    email: "sarah@example.com",
    phone_e164: null,
    external_identities: [],
    revision: 2,
    created_at: "2026-09-05T10:00:00Z",
    updated_at: "2026-09-05T10:00:00Z",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Candidate pages", () => {
  it("renders Candidate list summaries without exposing contact values", async () => {
    const response: CandidateListResponse = {
      items: [
        {
          id: candidateId,
          full_name: "Sarah Ahmed",
          current_title: "Backend Engineer",
          current_company: "Acme",
          location: "Bangalore",
          has_email: true,
          has_phone: false,
          revision: 2,
          updated_at: "2026-09-05T10:00:00Z",
        },
      ],
      limit: 100,
      offset: 0,
    };
    vi.mocked(candidatesApi.listCandidates).mockResolvedValue(response);

    renderWithQueryClient(<CandidatesPage />);

    expect(await screen.findByText("Sarah Ahmed")).toBeInTheDocument();
    expect(screen.getByText("Email available")).toBeInTheDocument();
    expect(screen.getByText("Phone missing")).toBeInTheDocument();
    expect(screen.queryByText("sarah@example.com")).not.toBeInTheDocument();
  });

  it("renders the Candidate list empty state", async () => {
    vi.mocked(candidatesApi.listCandidates).mockResolvedValue({
      items: [],
      limit: 100,
      offset: 0,
    });

    renderWithQueryClient(<CandidatesPage />);

    expect(await screen.findByText("No candidates found. Add a manual candidate to begin."))
      .toBeInTheDocument();
  });

  it("renders a Candidate list API error", async () => {
    vi.mocked(candidatesApi.listCandidates).mockRejectedValue(new Error("offline"));

    renderWithQueryClient(<CandidatesPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load candidates");
  });

  it("loads Candidate detail into the revision-safe editor", async () => {
    vi.mocked(candidatesApi.getCandidate).mockResolvedValue(candidate());

    renderWithQueryClient(<CandidateDetailPage />);

    expect(await screen.findByDisplayValue("Sarah Ahmed")).toBeInTheDocument();
    expect(screen.getByDisplayValue("sarah@example.com")).toBeInTheDocument();
    expect(screen.getByText("revision 2")).toBeInTheDocument();
  });

  it("renders a Candidate detail API error", async () => {
    vi.mocked(candidatesApi.getCandidate).mockRejectedValue(new Error("not found"));

    renderWithQueryClient(<CandidateDetailPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load this candidate");
  });
});
