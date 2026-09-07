"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { VoiceCallExecutionPanel } from "@/components/outreach/voice-call-execution";
import { ScreeningQuestionEditor } from "@/components/jobs/screening-question-editor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOutreachRequest } from "@/lib/outreach/api";
import { outreachKeys } from "@/lib/outreach/queries";

export function OutreachDetail({ outreachRequestId }: { outreachRequestId: string }) {
  const requestQuery = useQuery({
    queryKey: outreachKeys.detail(outreachRequestId),
    queryFn: () => getOutreachRequest(outreachRequestId),
  });
  const request = requestQuery.data;
  if (requestQuery.isLoading) return <p className="text-sm text-slate-500">Loading outreach…</p>;
  if (requestQuery.isError || !request) return <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">Unable to load outreach request.</div>;

  const questions = request.screening_questions.map((question) => ({
    ...question,
    client_key: question.id,
  }));
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">Immutable outreach request</p>
          <h1 className="text-3xl font-semibold tracking-tight">{request.requested_action}</h1>
          <p className="mt-2 text-sm text-slate-600">Created {new Date(request.created_at).toLocaleString()}</p>
        </div>
        <Button asChild variant="outline"><Link href="/outreach">All outreach</Link></Button>
      </div>
      {request.readiness === "STALE" ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Historical request preserved. Current state is stale: {request.stale_reasons.join(", ")}.
        </div>
      ) : null}
      <Card>
        <CardHeader><CardTitle>Frozen execution context</CardTitle></CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-2">
          <div><p className="text-slate-500">State</p><p className="font-medium">{request.readiness.replaceAll("_", " ")}</p></div>
          <div><p className="text-slate-500">Contact</p><p className="font-medium">{request.masked_phone}</p></div>
          <div><p className="text-slate-500">Screening context</p><p className="font-medium">{request.screening_questions.length} questions</p></div>
        </CardContent>
      </Card>
      <VoiceCallExecutionPanel outreachRequestId={outreachRequestId} ready={request.readiness === "READY_FOR_EXECUTION"} questions={request.screening_questions} />
      <Card>
        <CardHeader><CardTitle>Confirmed screening questions</CardTitle></CardHeader>
        <CardContent><ScreeningQuestionEditor value={questions} onChange={() => undefined} disabled /></CardContent>
      </Card>
    </div>
  );
}
