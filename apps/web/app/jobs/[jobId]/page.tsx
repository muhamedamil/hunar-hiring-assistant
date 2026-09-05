"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/layout/app-shell";
import { JobEditor } from "@/components/jobs/job-editor";
import { Skeleton } from "@/components/ui/skeleton";
import { getJob } from "@/lib/jobs/api";
import { jobKeys } from "@/lib/jobs/queries";

export default function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const jobQuery = useQuery({ queryKey: jobKeys.detail(jobId), queryFn: () => getJob(jobId) });

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        {jobQuery.isLoading ? <Skeleton className="h-96 w-full" /> : null}
        {jobQuery.isError ? (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            Unable to load this job.
          </div>
        ) : null}
        {jobQuery.data ? <JobEditor initialJob={jobQuery.data} /> : null}
      </div>
    </AppShell>
  );
}
