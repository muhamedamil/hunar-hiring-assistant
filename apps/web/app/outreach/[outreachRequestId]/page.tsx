"use client";

import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { OutreachDetail } from "@/components/outreach/outreach-detail";

export default function OutreachDetailPage() {
  const params = useParams<{ outreachRequestId: string }>();
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <OutreachDetail outreachRequestId={params.outreachRequestId} />
      </div>
    </AppShell>
  );
}
