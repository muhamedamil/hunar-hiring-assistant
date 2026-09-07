"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CallReadinessBadge } from "@/components/matching/call-readiness-badge";
import { MatchEvidence } from "@/components/matching/match-evidence";
import { MatchScore } from "@/components/matching/match-score";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import {
  evaluateJobCandidate,
  getJobCandidate,
  listJobCandidateMatches,
  updateShortlist,
} from "@/lib/matching/api";
import { matchingKeys } from "@/lib/matching/queries";
import type { ShortlistStatus } from "@/lib/matching/types";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unable to update this candidate review.";
}

export function JobCandidateDetail({ jobCandidateId }: { jobCandidateId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const detailQuery = useQuery({
    queryKey: matchingKeys.detail(jobCandidateId),
    queryFn: () => getJobCandidate(jobCandidateId),
  });
  const historyQuery = useQuery({
    queryKey: matchingKeys.matches(jobCandidateId),
    queryFn: () => listJobCandidateMatches(jobCandidateId),
  });
  const analyzeMutation = useMutation({
    mutationFn: () => evaluateJobCandidate(jobCandidateId),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: matchingKeys.detail(jobCandidateId) });
      void queryClient.invalidateQueries({ queryKey: matchingKeys.matches(jobCandidateId) });
    },
    onError: (value) => setError(errorMessage(value)),
  });
  const shortlistMutation = useMutation({
    mutationFn: ({ revision, status }: { revision: number; status: ShortlistStatus }) =>
      updateShortlist(jobCandidateId, revision, status),
    onSuccess: (detail) => {
      setError(null);
      queryClient.setQueryData(matchingKeys.detail(jobCandidateId), detail);
      void queryClient.invalidateQueries({ queryKey: matchingKeys.job(detail.job_id) });
    },
    onError: (value) => setError(errorMessage(value)),
  });

  const detail = detailQuery.data;
  const current = detail?.current_match ?? null;
  const pending = analyzeMutation.isPending || shortlistMutation.isPending;

  if (detailQuery.isLoading) return <p className="text-sm text-slate-500">Loading candidate review…</p>;
  if (detailQuery.isError || !detail) return <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Unable to load candidate review.</div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">Candidate ↔ Job review</p>
          <h1 className="text-3xl font-semibold tracking-tight">{detail.candidate.full_name}</h1>
          <p className="mt-2 text-sm text-slate-600">{detail.candidate.current_title ?? "Title unavailable"}{detail.candidate.location ? ` · ${detail.candidate.location}` : ""}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline"><Link href={`/jobs/${detail.job_id}/candidates`}>All candidates</Link></Button>
          <Button asChild variant="outline"><Link href={`/candidates/${detail.candidate.id}`}>Open candidate</Link></Button>
        </div>
      </div>

      {error ? <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div> : null}
      {!detail.match_freshness.is_fresh && current ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          This match is stale: {detail.match_freshness.stale_reasons.join(", ")}. Refresh it
          before confirming a shortlist decision.
        </div>
      ) : null}
      {
        current
        && detail.match_freshness.is_fresh
        && detail.shortlist_status !== "reviewing"
        && !detail.decision_is_current
          ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                The previous recruiter decision was made against an older match. Reconfirm the
                current match before downstream outreach can treat that decision as current.
              </div>
            )
          : null
      }
      {current?.semantic_failure_code ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Semantic analysis was unavailable ({current.semantic_failure_code}). Deterministic
          evidence remains visible and you can retry explicitly.
        </div>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Current assessment</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-2">
              <MatchScore match={current} />
              {!current ? (
                <p className="text-sm font-medium text-amber-800">Initial assessment unavailable</p>
              ) : null}
              <CallReadinessBadge value={detail.call_readiness} />
              <p className="text-xs text-slate-500">Shortlist state: {detail.shortlist_status.replace("_", " ")}{detail.decision_is_current ? " · current decision" : ""}</p>
            </div>
            <Button disabled={pending || detail.current_job_status !== "ready"} onClick={() => analyzeMutation.mutate()}>
              {analyzeMutation.isPending ? "Analyzing…" : current ? "Refresh match" : "Retry analysis"}
            </Button>
          </div>
          <MatchEvidence criteria={current?.match_reasons ?? []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Recruiter decision</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {detail.shortlist_status === "shortlisted"
            && detail.decision_is_current
            && detail.call_readiness === "ready" ? (
              <Button asChild>
                <Link href={`/job-candidates/${detail.id}/outreach`}>Prepare voice outreach</Link>
              </Button>
            ) : null}
          <Button
            disabled={pending || !current || !detail.match_freshness.is_fresh || detail.current_job_status !== "ready"}
            onClick={() => shortlistMutation.mutate({ revision: detail.revision, status: "shortlisted" })}
          >
            Shortlist
          </Button>
          <Button
            variant="outline"
            disabled={pending || !current || !detail.match_freshness.is_fresh || detail.current_job_status !== "ready"}
            onClick={() => shortlistMutation.mutate({ revision: detail.revision, status: "not_selected" })}
          >
            Not selected
          </Button>
          <Button
            variant="outline"
            disabled={
              pending
              || detail.shortlist_status === "reviewing"
              || detail.current_job_status !== "ready"
            }
            onClick={() => shortlistMutation.mutate({ revision: detail.revision, status: "reviewing" })}
          >
            Back to reviewing
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Match history</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {historyQuery.data?.items.map((match) => (
            <div key={match.id} className="rounded-lg border p-3 text-sm">
              <div className="flex flex-wrap justify-between gap-2">
                <span>Job definition v{match.definition_version} · {match.analysis_mode.replaceAll("_", " ")}</span>
                <span>{match.status}</span>
              </div>
              {match.match_score !== null ? <p className="mt-1 text-slate-500">Match {match.match_score}% · coverage {match.evidence_coverage}%</p> : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
