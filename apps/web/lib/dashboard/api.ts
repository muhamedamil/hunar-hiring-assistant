import { api } from "@/lib/api/client";
import type {
  DashboardOverview,
  DashboardScreeningDetail,
  DashboardScreeningFilters,
  DashboardScreeningListResponse,
} from "@/lib/dashboard/types";

export function getDashboardOverview(): Promise<DashboardOverview> {
  return api.get("/dashboard/overview");
}

export function listDashboardScreenings(
  filters: DashboardScreeningFilters = {},
): Promise<DashboardScreeningListResponse> {
  const params = new URLSearchParams();
  if (filters.jobId) params.set("job_id", filters.jobId);
  if (filters.state) params.set("state", filters.state);
  if (filters.interest) params.set("interest", filters.interest);
  if (filters.q !== undefined) {
    const normalized = filters.q.trim();
    if (normalized) params.set("q", normalized);
  }
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  return api.get(`/dashboard/screenings?${params.toString()}`);
}

export function getDashboardScreeningDetail(
  executionId: string,
): Promise<DashboardScreeningDetail> {
  return api.get(`/dashboard/screenings/${executionId}`);
}
