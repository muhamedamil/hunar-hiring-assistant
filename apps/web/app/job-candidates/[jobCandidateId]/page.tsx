"use client";

import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { JobCandidateDetail } from "@/components/matching/job-candidate-detail";

export default function JobCandidatePage() {
  const params = useParams<{ jobCandidateId: string }>();
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <JobCandidateDetail jobCandidateId={params.jobCandidateId} />
      </div>
    </AppShell>
  );
}
