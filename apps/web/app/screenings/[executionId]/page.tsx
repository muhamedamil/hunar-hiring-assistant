"use client";

import { useParams } from "next/navigation";

import { ScreeningDetail } from "@/components/dashboard/screening-detail";
import { AppShell } from "@/components/layout/app-shell";

export default function ScreeningDetailPage() {
  const params = useParams<{ executionId: string }>();
  return <AppShell><div className="mx-auto w-full max-w-6xl py-10"><ScreeningDetail executionId={params.executionId} /></div></AppShell>;
}
