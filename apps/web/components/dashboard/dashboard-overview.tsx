"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ScreeningStateBadge } from "@/components/dashboard/screening-state-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDashboardOverview } from "@/lib/dashboard/api";
import {
  attentionKindLabels,
  formatTimestamp,
  humanize,
} from "@/lib/dashboard/presentation";
import { dashboardKeys } from "@/lib/dashboard/queries";
import type { DashboardAttentionItem } from "@/lib/dashboard/types";

function attentionHref(item: DashboardAttentionItem): string {
  if (item.kind === "review_candidate") return `/job-candidates/${item.job_candidate_id}`;
  if ((item.kind === "result_invalid" || item.kind === "result_unavailable") && item.execution_id) {
    return `/screenings/${item.execution_id}`;
  }
  return item.outreach_request_id
    ? `/outreach/${item.outreach_request_id}`
    : `/job-candidates/${item.job_candidate_id}`;
}

export function DashboardOverview() {
  const query = useQuery({
    queryKey: dashboardKeys.overview,
    queryFn: getDashboardOverview,
    refetchInterval: 10_000,
  });

  if (query.isLoading) {
    return <p className="text-sm text-slate-500">Loading recruiting overview…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="text-sm text-rose-700">
        Unable to load the recruiting overview.
      </p>
    );
  }

  const data = query.data;
  const metrics = [
    ["Jobs", data.jobs.total],
    ["Candidates", data.candidates.total],
    ["Shortlisted", data.pipeline.shortlisted],
    ["Screening Results", data.screenings.result_available],
  ] as const;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Recruiting Overview</h1>
        <p className="mt-2 text-sm text-slate-600">
          Current recruiting activity from authoritative workflow data.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map(([label, value]) => (
          <Card key={label}>
            <CardContent className="pt-6">
              <p className="text-sm text-slate-500">{label}</p>
              <p className="mt-2 text-3xl font-semibold">{value}</p>
              {label === "Screening Results" ? (
                <p className="mt-1 text-xs text-slate-500">available</p>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Needs Attention</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.needs_attention.length === 0 ? (
            <p className="text-sm text-slate-500">Nothing needs attention right now.</p>
          ) : (
            data.needs_attention.map((item) => (
              <Link
                key={`${item.kind}-${item.execution_id ?? item.job_candidate_id}`}
                href={attentionHref(item)}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 hover:bg-slate-50"
              >
                <div>
                  <p className="font-medium">{item.candidate_name}</p>
                  <p className="text-sm text-slate-600">{item.job_title}</p>
                </div>
                <span className="text-sm font-medium text-slate-700">
                  {attentionKindLabels[item.kind]}
                </span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Voice Screenings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.recent_screenings.length === 0 ? (
            <p className="text-sm text-slate-500">No voice screenings yet.</p>
          ) : (
            data.recent_screenings.map((row) => (
              <Link
                key={row.execution_id}
                href={`/screenings/${row.execution_id}`}
                className="grid gap-2 rounded-lg border p-3 hover:bg-slate-50 md:grid-cols-[1.1fr_1.1fr_auto_auto_auto_auto] md:items-center"
              >
                <p className="font-medium">{row.candidate_name}</p>
                <p className="text-sm text-slate-600">{row.job_title}</p>
                <ScreeningStateBadge state={row.screening_state} />
                <p className="text-sm text-slate-600">{humanize(row.conversation_outcome)}</p>
                <p className="text-sm text-slate-600">{humanize(row.candidate_interest)}</p>
                <time className="text-xs text-slate-500" dateTime={row.sort_at}>
                  {formatTimestamp(row.sort_at)}
                </time>
              </Link>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
