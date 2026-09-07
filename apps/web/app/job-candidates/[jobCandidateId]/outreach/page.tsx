"use client";

import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { OutreachPreparation } from "@/components/outreach/outreach-preparation";

export default function OutreachPreparationPage() {
  const params = useParams<{ jobCandidateId: string }>();
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <OutreachPreparation jobCandidateId={params.jobCandidateId} />
      </div>
    </AppShell>
  );
}
