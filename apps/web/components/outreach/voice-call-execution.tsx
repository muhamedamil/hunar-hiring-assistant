"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { VoiceCallResultPanel } from "@/components/outreach/voice-call-result";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { submissionStatusLabels } from "@/lib/dashboard/presentation";
import { dashboardKeys } from "@/lib/dashboard/queries";
import { outreachKeys } from "@/lib/outreach/queries";
import type { VoiceCallExecution, VoiceScreeningOptions } from "@/lib/voice-calls/types";

export function VoiceCallExecutionPanel({ outreachRequestId, ready }: {
  outreachRequestId: string;
  ready: boolean;
}) {
  const client = useQueryClient();
  const key = ["voice-call", outreachRequestId];
  const [language, setLanguage] = useState("");
  const [timezone, setTimezone] = useState("");
  const options = useQuery({ queryKey: ["voice-screening-options"], queryFn: () => api.get<VoiceScreeningOptions>("/voice-screening/options") });
  const execution = useQuery({
    queryKey: key,
    queryFn: () => api.get<VoiceCallExecution | null>(`/outreach-requests/${outreachRequestId}/voice-call-execution`),
    refetchInterval: (query) => query.state.data && ["queued", "submitted", "unknown"].includes(query.state.data.status) ? 3_000 : false,
  });
  const dispatch = useMutation({
    mutationFn: () => execution.data?.status === "failed"
      ? api.post<VoiceCallExecution>(`/voice-call-executions/${execution.data.id}/retry`)
      : api.post<VoiceCallExecution>(`/outreach-requests/${outreachRequestId}/voice-call-executions`, { language: language || options.data?.default_language, timezone: timezone || options.data?.default_timezone }),
    retry: false,
    onSuccess: (result) => {
      client.setQueryData(key, result);
      void client.invalidateQueries({ queryKey: outreachKeys.all });
      void client.invalidateQueries({ queryKey: dashboardKeys.overview });
    },
    onError: () => { void client.invalidateQueries({ queryKey: key }); },
  });
  const row = execution.data;
  return <Card>
    <CardHeader><CardTitle>Voice Screening</CardTitle></CardHeader>
    <CardContent className="space-y-4 text-sm">
      {execution.isPending ? <p>Loading call submission…</p> : null}
      {execution.isError ? <p role="alert">Unable to load call submission.</p> : null}
      {row ? <>
        <div><p className="text-slate-500">Submission status</p><p role="status" className="font-medium">{submissionStatusLabels[row.status]}</p></div>
        <p className="text-slate-600">{row.language} · {row.timezone}</p>
        {row.status === "unknown" ? <p className="rounded-md bg-amber-50 p-3 text-amber-800">Submission certainty remains unknown. Do not resend unless the existing workflow explicitly permits it.</p> : null}
        {row.status === "failed" && ready ? <Button disabled={dispatch.isPending} onClick={() => dispatch.mutate()}>Retry dispatch</Button> : null}
        <VoiceCallResultPanel execution={row} />
      </> : !execution.isPending && !execution.isError && ready ? <>
        {options.isError ? <p role="alert">Unable to load voice screening options.</p> : null}
        {options.data?.languages.length === 0 ? <p>Voice screening is not configured yet.</p> : null}
        {options.data && options.data.languages.length > 0 ? <>
          <label className="block">Language<select className="ml-3 rounded border p-2" value={language || options.data.default_language} onChange={(e) => setLanguage(e.target.value)}>{options.data.languages.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label className="block">Timezone<select className="ml-3 rounded border p-2" value={timezone || options.data.default_timezone} onChange={(e) => setTimezone(e.target.value)}>{options.data.timezones.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <p>Automatic redials: Off</p>
          <Button disabled={dispatch.isPending} onClick={() => dispatch.mutate()}>Start voice screening</Button>
        </> : null}
      </> : null}
      {dispatch.isError ? <p role="alert">{dispatch.error instanceof ApiError ? dispatch.error.message : "Call submission could not proceed."}</p> : null}
    </CardContent>
  </Card>;
}
