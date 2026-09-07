import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/env", () => ({
  publicEnv: { apiBaseUrl: "http://api.test/api/v1" },
}));

import { api } from "@/lib/api/client";
import { listDashboardScreenings } from "@/lib/dashboard/api";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", { randomUUID: () => "request-123" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("parses successful JSON and sends a request id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get<{ status: string }>("/health/live")).resolves.toEqual({ status: "ok" });
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("X-Request-ID")).toBe("request-123");
  });

  it("maps the standard API error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "DATABASE_UNAVAILABLE",
              message: "Database is temporarily unavailable.",
              request_id: "req-1",
            },
          }),
          { status: 503 },
        ),
      ),
    );

    await expect(api.get("/health/ready")).rejects.toMatchObject({
      status: 503,
      code: "DATABASE_UNAVAILABLE",
      requestId: "req-1",
    });
  });

  it("keeps job_id as a programmatic screening filter and trims q", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 40 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listDashboardScreenings({
      jobId: "job-123",
      state: "result_available",
      interest: "interested",
      q: "  Aisha  ",
      limit: 20,
      offset: 40,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://api.test/api/v1/dashboard/screenings?job_id=job-123&state=result_available&interest=interested&q=Aisha&limit=20&offset=40",
    );
  });

  it("turns network failures into NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(api.get("/health/live")).rejects.toMatchObject({
      status: 0,
      code: "NETWORK_ERROR",
    });
  });
});
