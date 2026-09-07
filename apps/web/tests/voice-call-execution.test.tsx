import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { VoiceCallExecutionPanel } from "@/components/outreach/voice-call-execution";
import { api } from "@/lib/api/client";
import type { VoiceCallExecution } from "@/lib/voice-calls/types";

vi.mock("@/lib/api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
let execution: VoiceCallExecution | null;
const options = { languages: ["ENGLISH"], default_language: "ENGLISH", timezones: ["Asia/Kolkata", "Europe/London"], default_timezone: "Asia/Kolkata", automatic_redials: false };
function row(status: VoiceCallExecution["status"]): VoiceCallExecution {
  return { id: "execution", outreach_request_id: "outreach", status, language: "ENGLISH", timezone: "Asia/Kolkata", agent_contract_version: "hunar_voice_screening_en_v1", provider_call_id: null, provider_initial_status: null, failure_code: null, submitted_at: null, created_at: "2026-09-07T00:00:00Z", updated_at: "2026-09-07T00:00:00Z" };
}
function show(ready = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><VoiceCallExecutionPanel outreachRequestId="outreach" ready={ready} /></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  execution = null;
  vi.mocked(api.get).mockImplementation(async (path) => path.includes("options") ? options : execution);
  vi.mocked(api.post).mockResolvedValue(row("queued"));
});

it("starts only with configured language and chosen timezone, with redials off", async () => {
  const user = userEvent.setup();
  show();
  const start = await screen.findByRole("button", { name: "Start voice screening" });
  expect(screen.getByText("Automatic redials: Off")).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "HINDI" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Timezone"), "Europe/London");
  await user.click(start);
  expect(api.post).toHaveBeenCalledWith("/outreach-requests/outreach/voice-call-executions", { language: "ENGLISH", timezone: "Europe/London" });
  expect(await screen.findByText("Preparing voice call…")).toBeInTheDocument();
});

it("does not show Start for stale outreach", async () => {
  show(false);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it.each([
  ["queued", "Preparing voice call…"],
  ["submitted", "Call submitted to Hunar"],
  ["unknown", "Call submission outcome is uncertain."],
] as const)("renders %s without a retry action", async (status, label) => {
  execution = row(status);
  show();
  expect(await screen.findByText(label)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry dispatch" })).not.toBeInTheDocument();
  if (status === "submitted") expect(screen.getByText(/does not mean the call is complete/)).toBeInTheDocument();
});

it("retries FAILED by ID without modifying frozen inputs", async () => {
  execution = row("failed");
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Retry dispatch" }));
  expect(api.post).toHaveBeenCalledWith("/voice-call-executions/execution/retry");
});

it("hides retry when FAILED outreach has become stale", async () => {
  execution = row("failed");
  show(false);
  await screen.findByText("Call could not be submitted");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("fails closed if execution lookup fails", async () => {
  vi.mocked(api.get).mockRejectedValue(new Error("unavailable"));
  show();
  await screen.findByText("Unable to load call submission.");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
