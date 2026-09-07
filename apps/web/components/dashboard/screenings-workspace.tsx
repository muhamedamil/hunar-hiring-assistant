"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useMemo, useState } from "react";

import { ScreeningStateBadge } from "@/components/dashboard/screening-state-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { listDashboardScreenings } from "@/lib/dashboard/api";
import {
  formatTimestamp,
  humanize,
  isUnresolvedScreeningState,
  screeningStateLabels,
} from "@/lib/dashboard/presentation";
import { dashboardKeys } from "@/lib/dashboard/queries";
import type {
  CandidateInterest,
  DashboardScreeningFilters,
  DashboardScreeningState,
} from "@/lib/dashboard/types";

const PAGE_SIZE = 20;
const SCREENING_STATES = Object.entries(screeningStateLabels) as [
  DashboardScreeningState,
  string,
][];

export function ScreeningsWorkspace() {
  const params = useSearchParams();
  const jobId = params.get("job_id") ?? undefined;
  const [state, setState] = useState<DashboardScreeningState | "">("");
  const [interest, setInterest] = useState<CandidateInterest | "">("");
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState<string | undefined>();
  const [offset, setOffset] = useState(0);

  const filters = useMemo<DashboardScreeningFilters>(
    () => ({
      jobId,
      state: state || undefined,
      interest: interest || undefined,
      q,
      limit: PAGE_SIZE,
      offset,
    }),
    [interest, jobId, offset, q, state],
  );

  const query = useQuery({
    queryKey: dashboardKeys.screenings(filters),
    queryFn: () => listDashboardScreenings(filters),
    refetchInterval: (current) =>
      current.state.data?.items.some((row) => isUnresolvedScreeningState(row.screening_state))
        ? 5_000
        : false,
  });

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setQ(searchInput.trim() || undefined);
    setOffset(0);
  }

  const total = query.data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Screening Results</h1>
        <p className="mt-2 text-sm text-slate-600">
          Voice screening activity with server-side filters and pagination.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submitSearch} className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
            <Input
              aria-label="Search screenings"
              placeholder="Search candidate or role"
              value={searchInput}
              maxLength={100}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <select
              aria-label="Screening state"
              className="rounded-md border bg-white px-3 py-2 text-sm"
              value={state}
              onChange={(event) => {
                setState(event.target.value as DashboardScreeningState | "");
                setOffset(0);
              }}
            >
              <option value="">All states</option>
              {SCREENING_STATES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="Candidate interest"
              className="rounded-md border bg-white px-3 py-2 text-sm"
              value={interest}
              onChange={(event) => {
                setInterest(event.target.value as CandidateInterest | "");
                setOffset(0);
              }}
            >
              <option value="">All interest</option>
              <option value="interested">Interested</option>
              <option value="not_interested">Not interested</option>
              <option value="unclear">Unclear</option>
            </select>
            <Button type="submit">Search</Button>
          </form>
          {jobId ? (
            <p className="mt-3 text-xs text-slate-500">Showing a Job-scoped deep link.</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Voice Screenings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {query.isLoading ? <p className="text-sm text-slate-500">Loading screenings…</p> : null}
          {query.isError ? (
            <p role="alert" className="text-sm text-rose-700">
              Unable to load screenings.
            </p>
          ) : null}
          {query.data?.items.length === 0 ? (
            <p className="text-sm text-slate-500">No screenings match these filters.</p>
          ) : null}
          {query.data?.items.map((row) => (
            <Link
              key={row.execution_id}
              href={`/screenings/${row.execution_id}`}
              className="grid gap-2 rounded-lg border p-4 hover:bg-slate-50 md:grid-cols-[1.1fr_1.1fr_auto_auto_auto_auto_auto] md:items-center"
            >
              <p className="font-medium">{row.candidate_name}</p>
              <p className="text-sm text-slate-600">{row.job_title}</p>
              <ScreeningStateBadge state={row.screening_state} />
              <p className="text-sm text-slate-600">{humanize(row.conversation_outcome)}</p>
              <p className="text-sm text-slate-600">{humanize(row.candidate_interest)}</p>
              <p className="text-sm text-slate-600">
                {row.duration_seconds === null ? "—" : `${Math.round(row.duration_seconds)} sec`}
              </p>
              <time className="text-xs text-slate-500" dateTime={row.observed_at ?? undefined}>
                {formatTimestamp(row.observed_at)}
              </time>
            </Link>
          ))}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-sm text-slate-600">
            <p>
              {total === 0 ? "0 results" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0 || query.isFetching}
                onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={query.isFetching || offset + PAGE_SIZE >= total}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
