"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { SourcingStatusBadge } from "@/components/sourcing/sourcing-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import type { Job } from "@/lib/jobs/types";
import {
  enrichSourcingResult,
  getSourcingRun,
  listSourcingRuns,
  retrySourcingRun,
  startSourcingRun,
} from "@/lib/sourcing/api";
import { sourcingKeys } from "@/lib/sourcing/queries";
import type { SourcingEnrichment, SourcingRun } from "@/lib/sourcing/types";

const priorityLabels = {
  recommended: "Recommended to enrich",
  possible: "Possible",
  low_priority: "Low priority",
} as const;

const priorityStyles = {
  recommended: "border-emerald-200 bg-emerald-50 text-emerald-800",
  possible: "border-amber-200 bg-amber-50 text-amber-800",
  low_priority: "border-slate-200 bg-slate-50 text-slate-700",
} as const;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function persistedRunId(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== "object") {
    return null;
  }
  const value = (error.details as { run_id?: unknown }).run_id;
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function JobSourcingWorkspace({ job }: { job: Job }) {
  const router = useRouter();
  const [limit, setLimit] = useState<10 | 25 | 50>(25);
  const [error, setError] = useState<string | null>(null);
  const runsQuery = useQuery({
    queryKey: sourcingKeys.jobRuns(job.id),
    queryFn: () => listSourcingRuns(job.id),
  });
  const startMutation = useMutation({
    mutationFn: () => startSourcingRun(job.id, limit),
    onSuccess: (run) => router.push(`/sourcing/${run.id}`),
    onError: (value) => {
      const runId = persistedRunId(value);
      if (runId) {
        router.push(`/sourcing/${runId}`);
        return;
      }
      setError(errorMessage(value));
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">People sourcing</p>
          <h1 className="text-3xl font-semibold tracking-tight">{job.title}</h1>
          <p className="mt-2 text-sm text-slate-600">
            New searches bind to the currently approved Job definition. Historical runs keep
            their original version even if the Job is reopened later.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/jobs/${job.id}`}>Back to job</Link>
        </Button>
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Start a people search</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {job.status === "ready" ? (
            <>
              <p className="text-sm text-slate-600">
                This search will bind to approved definition v{job.approved_version}.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <label className="text-sm font-medium" htmlFor="result-limit">Results</label>
                <select
                  id="result-limit"
                  className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm"
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value) as 10 | 25 | 50)}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
                <Button
                  type="button"
                  disabled={startMutation.isPending}
                  onClick={() => {
                    setError(null);
                    startMutation.mutate();
                  }}
                >
                  {startMutation.isPending ? "Searching…" : "Find people"}
                </Button>
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              People search is unavailable while this Job is DRAFT. Mark the Job ready before
              starting new sourcing. Existing sourcing history remains available below.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sourcing history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {runsQuery.isLoading ? <p className="text-sm text-slate-500">Loading sourcing history…</p> : null}
          {runsQuery.isError ? (
            <p role="alert" className="text-sm text-rose-700">Unable to load sourcing history.</p>
          ) : null}
          {runsQuery.data?.items.length === 0 ? (
            <p className="text-sm text-slate-500">No sourcing runs yet.</p>
          ) : null}
          {runsQuery.data?.items.map((run) => (
            <Link
              key={run.id}
              href={`/sourcing/${run.id}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4 hover:bg-slate-50"
            >
              <div>
                <p className="font-medium">Approved definition v{run.definition_version}</p>
                <p className="text-sm text-slate-500">
                  {run.result_count} results · limit {run.result_limit}
                </p>
              </div>
              <SourcingStatusBadge status={run.status} />
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function enrichmentFor(run: SourcingRun, resultId: string): SourcingEnrichment | undefined {
  return run.enrichments.find((item) => item.sourcing_result_id === resultId);
}

export function SourcingRunWorkspace({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const runQuery = useQuery({
    queryKey: sourcingKeys.run(runId),
    queryFn: () => getSourcingRun(runId),
    refetchInterval: (query) => {
      const run = query.state.data;
      const activeEnrichment = run?.enrichments.some(
        (item) => item.status === "pending" || item.status === "awaiting_phone",
      );
      return run?.status === "searching" || activeEnrichment ? 3000 : false;
    },
  });
  const enrichMutation = useMutation({
    mutationFn: (resultId: string) => enrichSourcingResult(resultId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sourcingKeys.run(runId) }),
    onError: (value) => setError(errorMessage(value)),
  });
  const retryMutation = useMutation({
    mutationFn: () => retrySourcingRun(runId),
    onSuccess: (run) => queryClient.setQueryData(sourcingKeys.run(runId), run),
    onError: (value) => {
      setError(errorMessage(value));
      void queryClient.invalidateQueries({ queryKey: sourcingKeys.run(runId) });
    },
  });

  if (runQuery.isLoading) return <p className="text-sm text-slate-500">Loading sourcing run…</p>;
  if (runQuery.isError || !runQuery.data) {
    return <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Unable to load this sourcing run.</div>;
  }

  const run = runQuery.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <SourcingStatusBadge status={run.status} />
            <span className="text-xs text-slate-500">approved Job v{run.definition_version}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">People search</h1>
          <p className="mt-2 text-sm text-slate-600">
            Apollo search evidence only. Matching and shortlisting happen in a later module.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/jobs/${run.job_id}/sourcing`}>Back to sourcing history</Link>
        </Button>
      </div>

      {error ? <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div> : null}

      <Card>
        <CardHeader><CardTitle>Search criteria actually used</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Titles</p>
            <p className="mt-1 text-sm">{run.criteria.titles.join(", ")}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Locations</p>
            <p className="mt-1 text-sm">{run.criteria.locations.join(", ") || "Not specified"}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Seniority</p>
            <p className="mt-1 text-sm">{run.criteria.seniorities.join(", ") || "Not directly filtered"}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Provider mapping</p>
            <p className="mt-1 text-sm">{run.mapping_version}</p>
          </div>
          <div className="md:col-span-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Not directly filtered by Apollo</p>
            {run.criteria.unmapped_requirements.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {run.criteria.unmapped_requirements.map((item) => (
                  <li key={item.field}>{item.field}: {item.values.join(", ")}</li>
                ))}
              </ul>
            ) : <p className="mt-1 text-sm text-slate-500">None</p>}
          </div>
        </CardContent>
      </Card>

      {run.status === "failed" ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-6">
            <div>
              <p className="font-medium">Search failed</p>
              <p className="text-sm text-slate-500">{run.failure_code ?? "Provider search failed."}</p>
            </div>
            <Button disabled={retryMutation.isPending} onClick={() => retryMutation.mutate()}>
              {retryMutation.isPending ? "Retrying…" : "Retry same search"}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Search results ({run.result_count})</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {run.status === "completed" && run.results.length === 0 ? (
            <p className="text-sm text-slate-500">Apollo returned no people for this bounded search.</p>
          ) : null}
          {run.results.map((result) => {
            const enrichment = enrichmentFor(run, result.id);
            const name = [result.first_name, result.last_name_obfuscated].filter(Boolean).join(" ") || "Unnamed Apollo result";
            return (
              <div key={result.id} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="font-medium">{name}</p>
                    <p className="text-sm text-slate-600">{result.current_title ?? "Title unavailable"}{result.organization_name ? ` · ${result.organization_name}` : ""}</p>
                    <p className="mt-2 text-xs text-slate-500">
                      {result.email_available ? "Email may be available" : "Email availability unknown"} · phone {result.phone_availability}
                    </p>
                    <div
                      className={`mt-3 rounded-md border p-3 text-sm ${priorityStyles[result.enrichment_priority]}`}
                    >
                      <p className="font-medium">
                        {priorityLabels[result.enrichment_priority]}
                      </p>
                      <ul className="mt-1 list-disc space-y-0.5 pl-5">
                        {result.enrichment_priority_reasons.map((reason) => (
                          <li key={reason.code}>{reason.detail}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {enrichment ? <SourcingStatusBadge status={enrichment.status} /> : null}
                    {enrichment?.candidate_id ? (
                      <Button asChild variant="outline" size="sm"><Link href={`/candidates/${enrichment.candidate_id}`}>Open candidate</Link></Button>
                    ) : null}
                    {!enrichment ? (
                      <Button
                        size="sm"
                        disabled={enrichMutation.isPending}
                        onClick={() => {
                          setError(null);
                          enrichMutation.mutate(result.id);
                        }}
                      >
                        Enrich contact
                      </Button>
                    ) : null}
                  </div>
                </div>
                {enrichment?.status === "pending" ? (
                  <p className="mt-3 text-sm text-slate-600">Contact enrichment is queued.</p>
                ) : null}
                {enrichment?.status === "awaiting_phone" ? (
                  <p className="mt-3 text-sm text-slate-600">
                    Candidate resolved. Waiting for Apollo phone result…
                  </p>
                ) : null}
                {enrichment?.status === "completed" ? (
                  <p className="mt-3 text-sm text-emerald-700">
                    Enrichment completed. Canonical contact details are available on the Candidate.
                  </p>
                ) : null}
                {enrichment?.status === "failed" ? (
                  <p className="mt-3 text-sm text-rose-700">
                    Enrichment failed{enrichment.failure_code ? `: ${enrichment.failure_code}` : "."}
                  </p>
                ) : null}
                {enrichment?.status === "conflict" ? (
                  <p className="mt-3 text-sm text-rose-700">Candidate identity conflict. No records were merged automatically.</p>
                ) : null}
                {enrichment?.status === "unknown" ? (
                  <p className="mt-3 text-sm text-amber-800">Apollo enrichment outcome is uncertain and was not retried automatically.</p>
                ) : null}
                {enrichment?.status === "not_found" ? (
                  <p className="mt-3 text-sm text-slate-600">Apollo could not enrich this person.</p>
                ) : null}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
