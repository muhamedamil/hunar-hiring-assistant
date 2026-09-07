import type { DashboardScreeningFilters } from "@/lib/dashboard/types";

export const dashboardKeys = {
  all: ["dashboard"] as const,
  overview: ["dashboard", "overview"] as const,
  screenings(filters: DashboardScreeningFilters) {
    return ["dashboard", "screenings", filters] as const;
  },
  screening(executionId: string) {
    return ["dashboard", "screening", executionId] as const;
  },
};
