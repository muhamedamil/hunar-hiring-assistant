"use client";

import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { SourcingRunWorkspace } from "@/components/sourcing/sourcing-workspace";

export default function SourcingRunPage() {
  const params = useParams<{ runId: string }>();

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <SourcingRunWorkspace runId={params.runId} />
      </div>
    </AppShell>
  );
}
