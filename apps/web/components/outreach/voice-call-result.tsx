"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { ScreeningDetailContent } from "@/components/dashboard/screening-detail-content";
import { getDashboardScreeningDetail } from "@/lib/dashboard/api";
import { isUnresolvedScreeningState } from "@/lib/dashboard/presentation";
import { dashboardKeys } from "@/lib/dashboard/queries";
import { outreachKeys } from "@/lib/outreach/queries";
import type { VoiceCallExecution } from "@/lib/voice-calls/types";

export function VoiceCallResultPanel({ execution }: { execution: VoiceCallExecution }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: dashboardKeys.screening(execution.id),
    queryFn: () => getDashboardScreeningDetail(execution.id),
    refetchInterval: (current) => current.state.data && isUnresolvedScreeningState(current.state.data.screening_state) ? 3_000 : false,
  });
  const state = query.data?.screening_state;
  useEffect(() => {
    if (state && !isUnresolvedScreeningState(state)) {
      void client.invalidateQueries({ queryKey: outreachKeys.all });
      void client.invalidateQueries({ queryKey: dashboardKeys.overview });
    }
  }, [client, state]);

  if (query.isLoading) return <p className="text-sm text-slate-500">Loading screening status…</p>;
  if (query.isError || !query.data) return <p role="alert" className="text-sm text-rose-700">Unable to load recruiter-safe screening status.</p>;
  return <ScreeningDetailContent detail={query.data} showIdentity={false} />;
}
