"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { CandidateEditor } from "@/components/candidates/candidate-editor";
import { AppShell } from "@/components/layout/app-shell";
import { Skeleton } from "@/components/ui/skeleton";
import { getCandidate } from "@/lib/candidates/api";
import { candidateKeys } from "@/lib/candidates/queries";

export default function CandidateDetailPage() {
  const params = useParams<{ candidateId: string }>();
  const candidateId = params.candidateId;
  const candidateQuery = useQuery({
    queryKey: candidateKeys.detail(candidateId),
    queryFn: () => getCandidate(candidateId),
  });

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        {candidateQuery.isLoading ? <Skeleton className="h-96 w-full" /> : null}
        {candidateQuery.isError ? (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            Unable to load this candidate.
          </div>
        ) : null}
        {candidateQuery.data ? <CandidateEditor initialCandidate={candidateQuery.data} /> : null}
      </div>
    </AppShell>
  );
}
