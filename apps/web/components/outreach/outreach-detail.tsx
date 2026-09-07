"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ScreeningStateBadge } from "@/components/dashboard/screening-state-badge";
import { VoiceCallExecutionPanel } from "@/components/outreach/voice-call-execution";
import { ScreeningQuestionEditor } from "@/components/jobs/screening-question-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOutreachRequest } from "@/lib/outreach/api";
import { outreachKeys } from "@/lib/outreach/queries";

export function OutreachDetail({ outreachRequestId }: { outreachRequestId: string }) {
  const requestQuery = useQuery({
    queryKey: outreachKeys.detail(outreachRequestId),
    queryFn: () => getOutreachRequest(outreachRequestId),
    refetchInterval: 5_000,
  });
  const request = requestQuery.data;
  if (requestQuery.isLoading) return <p className="text-sm text-slate-500">Loading outreach…</p>;
  if (requestQuery.isError || !request) return <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Unable to load outreach request.</div>;

  const questions = request.screening_questions.map((question) => ({ ...question, client_key: question.id }));
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-semibold tracking-tight">Voice Screening Outreach</h1><p className="mt-2 text-sm text-slate-600">Created {new Date(request.created_at).toLocaleString()}</p></div>
        <Button asChild variant="outline"><Link href="/outreach">All outreach</Link></Button>
      </div>
      {request.readiness === "STALE" ? <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">Historical outreach preserved. Current upstream context changed; execution actions remain fail-closed.</div> : null}
      <Card>
        <CardHeader><CardTitle>Candidate &amp; Role</CardTitle></CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-2">
          <div><p className="text-slate-500">Candidate</p><p className="font-medium">{request.candidate_name}</p></div>
          <div><p className="text-slate-500">Role</p><p className="font-medium">{request.job_title}</p></div>
          <div><p className="text-slate-500">Historical Job version</p><p className="font-medium">v{request.job_definition_version}</p></div>
          <div><p className="text-slate-500">Current state</p><div className="mt-1">{request.screening_state ? <ScreeningStateBadge state={request.screening_state} /> : request.readiness === "READY_FOR_EXECUTION" ? <Badge className="bg-emerald-100 text-emerald-800">Ready for execution</Badge> : <Badge className="bg-amber-100 text-amber-800">Outreach context changed</Badge>}</div></div>
        </CardContent>
      </Card>
      <VoiceCallExecutionPanel outreachRequestId={outreachRequestId} ready={request.readiness === "READY_FOR_EXECUTION"} />
      <Card>
        <CardHeader><CardTitle>Confirmed Screening Questions</CardTitle></CardHeader>
        <CardContent><ScreeningQuestionEditor value={questions} onChange={() => undefined} disabled /></CardContent>
      </Card>
    </div>
  );
}
