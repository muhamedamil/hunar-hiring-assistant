"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { CandidateContactStatus } from "@/components/candidates/candidate-contact-status";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { listCandidates } from "@/lib/candidates/api";
import { candidateKeys } from "@/lib/candidates/queries";

export default function CandidatesPage() {
  const [query, setQuery] = useState("");
  const candidatesQuery = useQuery({
    queryKey: candidateKeys.list(query),
    queryFn: () => listCandidates(query),
  });

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl space-y-6 py-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-500">Global identity</p>
            <h1 className="text-3xl font-semibold tracking-tight">Candidates</h1>
            <p className="mt-2 text-sm text-slate-600">
              Manual and future sourced people converge on the same Candidate Core.
            </p>
          </div>
          <Button asChild>
            <Link href="/candidates/new">Add candidate</Link>
          </Button>
        </div>

        <Input
          aria-label="Search candidates"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, title, company, or location"
          className="max-w-xl"
        />

        {candidatesQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : null}

        {candidatesQuery.isError ? (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            Unable to load candidates. Retry after confirming the API and database are available.
          </div>
        ) : null}

        {candidatesQuery.data?.items.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm text-slate-600">
              No candidates found. Add a manual candidate to begin.
            </CardContent>
          </Card>
        ) : null}

        <div className="space-y-3">
          {candidatesQuery.data?.items.map((candidate) => (
            <Link key={candidate.id} href={`/candidates/${candidate.id}`} className="block">
              <Card className="transition-shadow hover:shadow-md">
                <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                  <div>
                    <div className="font-medium text-slate-950">{candidate.full_name}</div>
                    <div className="mt-1 text-sm text-slate-500">
                      {candidate.current_title || "Title not specified"}
                      {candidate.current_company ? ` · ${candidate.current_company}` : ""}
                    </div>
                    {candidate.location ? (
                      <div className="mt-1 text-xs text-slate-400">{candidate.location}</div>
                    ) : null}
                  </div>
                  <div className="space-y-2 text-right">
                    <CandidateContactStatus
                      hasEmail={candidate.has_email}
                      hasPhone={candidate.has_phone}
                    />
                    <span className="text-xs text-slate-400">rev {candidate.revision}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
