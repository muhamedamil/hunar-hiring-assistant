"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { getCallResult, reconcileCallResult } from "@/lib/call-results/api";
import { callResultKeys } from "@/lib/call-results/queries";
import type { VoiceCallResult } from "@/lib/call-results/types";
import type { OutreachQuestion } from "@/lib/outreach/types";
import type { VoiceCallExecution } from "@/lib/voice-calls/types";

function terminalMessage(result: VoiceCallResult): string | null {
  if (result.lifecycle_status === "NOT_CONNECTED") return "Candidate was not connected.";
  if (result.lifecycle_status === "FAILED") return "Call failed before screening completed.";
  if (result.lifecycle_status === "CANCELLED") return "Call was cancelled.";
  if (result.answered_by === "MACHINE") {
    return "Call completed, but Hunar detected a machine/voicemail rather than a human. No screening answers were accepted.";
  }
  if (result.answered_by !== "HUMAN") {
    return "Call completed, but a human answer could not be verified safely. No screening answers were accepted.";
  }
  if (result.screening_result_state === "invalid") {
    return "Call completed, but the provider result could not be safely mapped to the confirmed questions.";
  }
  if (result.screening_result_state === "unavailable") {
    return "Call completed, but a structured screening result is not available.";
  }
  return null;
}

function answerLabel(state: string, text: string | null): string {
  if (state === "no_clear_answer") return "No clear answer";
  if (state === "not_asked") return "Not asked";
  return text ?? "";
}

export function VoiceCallResultPanel({ execution, questions }: {
  execution: VoiceCallExecution;
  questions: OutreachQuestion[];
}) {
  const client = useQueryClient();
  const key = callResultKeys.detail(execution.id);
  const resultQuery = useQuery({
    queryKey: key,
    queryFn: () => getCallResult(execution.id),
    refetchInterval: (query) => query.state.data ? false : 3000,
    enabled: ["queued", "submitted", "unknown"].includes(execution.status),
  });
  const reconcile = useMutation({
    mutationFn: () => reconcileCallResult(execution.id),
    retry: false,
    onSuccess: (response) => client.setQueryData(key, response.result),
  });
  const result = resultQuery.data;
  if (!result) {
    if (execution.status === "unknown" && execution.provider_call_id) {
      return <div className="space-y-2">
        <p>Submission outcome was uncertain, but a provider call identity is available.</p>
        <Button onClick={() => reconcile.mutate()} disabled={reconcile.isPending}>Check Hunar safely</Button>
        {reconcile.isError ? <p role="alert">Safe reconciliation could not be completed.</p> : null}
      </div>;
    }
    if (execution.status === "unknown") {
      return <p>Submission outcome is uncertain. No safe provider call identity is available. Do not resend the call.</p>;
    }
    if (execution.status === "queued" || execution.status === "submitted") {
      return <p>Awaiting call outcome…</p>;
    }
    return null;
  }
  const message = terminalMessage(result);
  if (message) return <div className="space-y-2"><p>{message}</p>
    {result.recording_available ? <p>Recording available</p> : null}
    {result.lifecycle_status === "COMPLETED" && execution.provider_call_id ?
      <Button onClick={() => reconcile.mutate()} disabled={reconcile.isPending}>Refresh result from Hunar</Button> : null}
  </div>;
  const byId = new Map(questions.map((question) => [question.id, question]));
  return <div className="space-y-3">
    <p className="font-medium">Screening completed</p>
    <dl className="grid gap-2 md:grid-cols-3">
      <div><dt>Conversation outcome</dt><dd>{result.conversation_outcome}</dd></div>
      <div><dt>Candidate interest</dt><dd>{result.candidate_interest}</dd></div>
      <div><dt>Duration</dt><dd>{result.duration_seconds ?? "Not available"}</dd></div>
    </dl>
    <div><p className="font-medium">Screening answers</p><ol className="list-decimal pl-5">
      {result.answers.map((answer) => <li key={answer.outreach_question_id}>
        <p>{byId.get(answer.outreach_question_id)?.prompt ?? `Question ${answer.position}`}</p>
        <p>{answerLabel(answer.answer_state, answer.answer_text)}</p>
      </li>)}
    </ol></div>
    {result.recording_available ? <p>Recording available</p> : null}
  </div>;
}
