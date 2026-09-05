import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateEditor } from "@/components/candidates/candidate-editor";
import { ApiError } from "@/lib/api/errors";
import * as candidatesApi from "@/lib/candidates/api";
import type { Candidate } from "@/lib/candidates/types";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/candidates/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/candidates/api")>(
    "@/lib/candidates/api",
  );
  return {
    ...actual,
    createCandidate: vi.fn(),
    updateCandidate: vi.fn(),
  };
});

function renderEditor(initialCandidate?: Candidate) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CandidateEditor initialCandidate={initialCandidate} />
    </QueryClientProvider>,
  );
}

function candidate(): Candidate {
  return {
    id: "11111111-1111-4111-8111-111111111111",
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

describe("CandidateEditor", () => {
  it("creates a valid name-only Candidate without requiring contact details", async () => {
    const created = { ...candidate(), email: null, current_title: null, current_company: null, location: null, revision: 0 };
    vi.mocked(candidatesApi.createCandidate).mockResolvedValue(created);

    renderEditor();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Full name"), "Sarah Ahmed");
    await user.click(screen.getByRole("button", { name: "Create candidate" }));

    await screen.findByText("Candidate created.");
    expect(candidatesApi.createCandidate).toHaveBeenCalledWith({
      full_name: "Sarah Ahmed",
      current_title: null,
      current_company: null,
      location: null,
      email: null,
      phone: null,
    });
    expect(replace).toHaveBeenCalledWith(`/candidates/${created.id}`);
  });

  it("shows an actionable link when strong contact identity already exists", async () => {
    vi.mocked(candidatesApi.createCandidate).mockRejectedValue(
      new ApiError(
        409,
        "CANDIDATE_ALREADY_EXISTS",
        "A candidate with this contact already exists.",
        "request-1",
        { existing_candidate_id: "22222222-2222-4222-8222-222222222222" },
      ),
    );

    renderEditor();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Full name"), "Sarah Ahmed");
    await user.type(screen.getByLabelText("Email"), "sarah@example.com");
    await user.click(screen.getByRole("button", { name: "Create candidate" }));

    const link = await screen.findByRole("link", { name: "Open existing candidate" });
    expect(link).toHaveAttribute(
      "href",
      "/candidates/22222222-2222-4222-8222-222222222222",
    );
  });

  it("requires an explicit international country code before submitting a phone", async () => {
    renderEditor();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Sarah Ahmed" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "9876543210" } });
    fireEvent.click(screen.getByRole("button", { name: "Create candidate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Phone must include an international country code",
    );
    expect(candidatesApi.createCandidate).not.toHaveBeenCalled();
  });

  it("uses the loaded revision when saving Candidate profile changes", async () => {
    const current = candidate();
    vi.mocked(candidatesApi.updateCandidate).mockResolvedValue({
      ...current,
      current_title: "Senior Backend Engineer",
      revision: 3,
    });

    renderEditor(current);
    const user = userEvent.setup();
    await user.clear(screen.getByLabelText("Current title"));
    await user.type(screen.getByLabelText("Current title"), "Senior Backend Engineer");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(candidatesApi.updateCandidate).toHaveBeenCalledWith(
        current.id,
        current.revision,
        expect.objectContaining({ current_title: "Senior Backend Engineer" }),
      ),
    );
    expect(await screen.findByText("Candidate changes saved.")).toBeInTheDocument();
  });

  it("surfaces a stale revision conflict instead of silently overwriting", async () => {
    const current = candidate();
    vi.mocked(candidatesApi.updateCandidate).mockRejectedValue(
      new ApiError(
        409,
        "CANDIDATE_REVISION_CONFLICT",
        "Candidate changed since it was loaded. Reload the latest version before saving.",
      ),
    );

    renderEditor(current);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Reload the latest version before saving",
    );
  });
});
