"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ScreeningDetailContent } from "@/components/dashboard/screening-detail-content";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { getDashboardScreeningDetail } from "@/lib/dashboard/api";
import { isUnresolvedScreeningState } from "@/lib/dashboard/presentation";
import { dashboardKeys } from "@/lib/dashboard/queries";

export function ScreeningDetail({ executionId }: { executionId: string }) {
  const query = useQuery({
    queryKey: dashboardKeys.screening(executionId),
    queryFn: () => getDashboardScreeningDetail(executionId),
    refetchInterval: (current) => current.state.data && isUnresolvedScreeningState(current.state.data.screening_state) ? 5_000 : false,
  });
  if (query.isLoading) return <p className="text-sm text-slate-500">Loading screening…</p>;
  if (query.isError || !query.data) {
    const error = query.error;
    const message = error instanceof ApiError && error.status === 404
      ? "Screening execution was not found."
      : error instanceof ApiError && error.code === "DASHBOARD_HISTORICAL_CONTEXT_INVALID"
        ? "Screening historical context is inconsistent and cannot be displayed safely."
        : "Unable to load screening detail.";
    return <div className="space-y-4"><p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{message}</p><Button asChild variant="outline"><Link href="/screenings">Back to screenings</Link></Button></div>;
  }
  return <div className="space-y-6"><div className="flex items-center justify-between gap-3"><div><h1 className="text-3xl font-semibold tracking-tight">Screening Detail</h1><p className="mt-2 text-sm text-slate-600">Historical screening context and normalized answers.</p></div><Button asChild variant="outline"><Link href="/screenings">All screenings</Link></Button></div><ScreeningDetailContent detail={query.data} /></div>;
}
