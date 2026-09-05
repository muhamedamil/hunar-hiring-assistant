"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/app-shell";
import { JobStatusBadge } from "@/components/jobs/job-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listJobs } from "@/lib/jobs/api";
import { jobKeys } from "@/lib/jobs/queries";

export default function JobsPage() {
  const jobsQuery = useQuery({ queryKey: jobKeys.all, queryFn: () => listJobs() });

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl space-y-6 py-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-500">Hiring definitions</p>
            <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
            <p className="mt-2 text-sm text-slate-600">
              Ready versions become the shared source of truth for sourcing and voice screening.
            </p>
          </div>
          <Button asChild>
            <Link href="/jobs/new">Create job</Link>
          </Button>
        </div>

        {jobsQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : null}

        {jobsQuery.isError ? (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            Unable to load jobs. Retry after confirming the API and database are available.
          </div>
        ) : null}

        {jobsQuery.data?.items.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm text-slate-600">
              No jobs yet. Create the first hiring definition to begin.
            </CardContent>
          </Card>
        ) : null}

        <div className="space-y-3">
          {jobsQuery.data?.items.map((job) => (
            <Link key={job.id} href={`/jobs/${job.id}`} className="block">
              <Card className="transition-shadow hover:shadow-md">
                <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                  <div>
                    <div className="font-medium text-slate-950">{job.title}</div>
                    <div className="mt-1 text-sm text-slate-500">
                      {job.company_name || "Company not specified"} · Updated {new Date(job.updated_at).toISOString().slice(0, 10)}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <JobStatusBadge status={job.status} version={job.approved_version} />
                    <span className="text-xs text-slate-400">rev {job.revision}</span>
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
