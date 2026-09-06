"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CallReadinessBadge } from "@/components/matching/call-readiness-badge";
import { MatchScore } from "@/components/matching/match-score";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { listCandidates } from "@/lib/candidates/api";
import { candidateKeys } from "@/lib/candidates/queries";
import type { Job } from "@/lib/jobs/types";
import { addManualJobCandidate, listJobCandidates } from "@/lib/matching/api";
import { matchingKeys } from "@/lib/matching/queries";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unable to update candidate review state.";
}

const PAGE_SIZE = 20;

export function JobCandidateWorkspace({ job }: { job: Job }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const relationsQuery = useQuery({
    queryKey: [...matchingKeys.job(job.id), offset],
    queryFn: () => listJobCandidates(job.id, undefined, PAGE_SIZE, offset),
  });
  const candidatesQuery = useQuery({
    queryKey: candidateKeys.list(query),
    queryFn: () => listCandidates(query),
    enabled: job.status === "ready",
  });
  const addMutation = useMutation({
    mutationFn: (candidateId: string) => addManualJobCandidate(job.id, candidateId),
    onSuccess: (relation) => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: matchingKeys.job(job.id) });
      router.push(`/job-candidates/${relation.id}`);
    },
    onError: (value) => setError(errorMessage(value)),
  });

  const attachedIds = new Set(relationsQuery.data?.items.map((item) => item.candidate.id) ?? []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">Candidate review</p>
          <h1 className="text-3xl font-semibold tracking-tight">{job.title}</h1>
          <p className="mt-2 text-sm text-slate-600">
            Manual and Apollo-resolved candidates share one match and shortlist workflow.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline"><Link href={`/jobs/${job.id}/sourcing`}>Find people</Link></Button>
          <Button asChild variant="outline"><Link href={`/jobs/${job.id}`}>Back to job</Link></Button>
        </div>
      </div>

      {error ? <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div> : null}

      {job.status === "ready" ? (
        <Card>
          <CardHeader><CardTitle>Add existing candidate</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Input
              aria-label="Search candidates to add"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search Candidate Core by name, title, company, or location"
            />
            <div className="space-y-2">
              {candidatesQuery.data?.items.slice(0, 8).map((candidate) => (
                <div key={candidate.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
                  <div>
                    <p className="font-medium">{candidate.full_name}</p>
                    <p className="text-sm text-slate-500">{candidate.current_title ?? "Title unavailable"}{candidate.location ? ` · ${candidate.location}` : ""}</p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={attachedIds.has(candidate.id) || addMutation.isPending}
                    onClick={() => addMutation.mutate(candidate.id)}
                  >
                    {attachedIds.has(candidate.id) ? "Added" : "Add to job"}
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          This Job is DRAFT. Historical candidate reviews remain visible, but new relationships and match refreshes are blocked until it is READY again.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Candidates</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {relationsQuery.data?.items.length === 0 ? <p className="text-sm text-slate-500">No candidates are attached to this Job yet.</p> : null}
          {relationsQuery.data?.items.map((item) => (
            <Link
              key={item.id}
              href={`/job-candidates/${item.id}`}
              className="block rounded-lg border p-4 transition-shadow hover:shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-medium">{item.candidate.full_name}</p>
                  <p className="text-sm text-slate-500">{item.candidate.current_title ?? "Title unavailable"}{item.candidate.location ? ` · ${item.candidate.location}` : ""}</p>
                  <p className="mt-1 text-xs text-slate-400">Source: {item.created_source} · {item.shortlist_status.replace("_", " ")}</p>
                </div>
                <div className="space-y-2 text-right">
                  <MatchScore match={item.current_match} />
                  <CallReadinessBadge value={item.call_readiness} />
                  {!item.match_freshness.is_fresh && item.current_match ? <p className="text-xs text-amber-700">Match refresh required</p> : null}
                </div>
              </div>
            </Link>
          ))}
          <div className="flex items-center justify-between gap-3 pt-2">
            <p className="text-xs text-slate-500">
              Showing {relationsQuery.data?.items.length ?? 0} candidates from offset {offset}.
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={offset === 0 || relationsQuery.isFetching}
                onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={
                  relationsQuery.isFetching
                  || (relationsQuery.data?.items.length ?? 0) < PAGE_SIZE
                }
                onClick={() => setOffset((current) => current + PAGE_SIZE)}
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
