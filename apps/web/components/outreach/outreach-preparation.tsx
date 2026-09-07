"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  type EditableQuestion,
  ScreeningQuestionEditor,
} from "@/components/jobs/screening-question-editor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import { getOutreachPreparation, prepareOutreach } from "@/lib/outreach/api";
import { outreachKeys } from "@/lib/outreach/queries";
import type { OutreachQuestionDraft } from "@/lib/outreach/types";

function editableQuestions(questions: OutreachQuestionDraft[]): EditableQuestion[] {
  return questions.map((question) => ({
    ...question,
    client_key:
      question.source_job_question_id
      ?? globalThis.crypto?.randomUUID?.()
      ?? `question-${Date.now()}-${Math.random()}`,
  }));
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unable to confirm this outreach request.";
}

export function OutreachPreparation({ jobCandidateId }: { jobCandidateId: string }) {
  const router = useRouter();
  const [questions, setQuestions] = useState<EditableQuestion[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preparationQuery = useQuery({
    queryKey: outreachKeys.preparation(jobCandidateId),
    queryFn: () => getOutreachPreparation(jobCandidateId),
  });
  const preparation = preparationQuery.data;

  useEffect(() => {
    if (preparation && !seeded) {
      setQuestions(editableQuestions(preparation.default_screening_questions));
      setSeeded(true);
    }
  }, [preparation, seeded]);

  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!preparation) throw new Error("Preparation is unavailable.");
      return prepareOutreach(jobCandidateId, {
        preparation_token: preparation.preparation_token,
        screening_questions: questions.map((question) => ({
          source_job_question_id: question.source_job_question_id ?? null,
          key: question.key,
          prompt: question.prompt,
          answer_type: question.answer_type,
          required: question.required,
          options: question.options,
        })),
      });
    },
    onSuccess: (request) => router.push(`/outreach/${request.id}`),
    onError: (value) => setError(errorMessage(value)),
  });

  if (preparationQuery.isLoading) {
    return <p className="text-sm text-slate-500">Loading outreach preparation…</p>;
  }
  if (preparationQuery.isError || !preparation) {
    return (
      <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        Outreach cannot be prepared from the current shortlist state.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">Outreach request</p>
          <h1 className="text-3xl font-semibold tracking-tight">{preparation.candidate_name}</h1>
          <p className="mt-2 text-sm text-slate-600">{preparation.role}</p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/job-candidates/${jobCandidateId}`}>Back to review</Link>
        </Button>
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {error} Reload preparation before confirming again.
        </div>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Execution context</CardTitle></CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-2">
          <div><p className="text-slate-500">Approved Job version</p><p className="font-medium">v{preparation.definition_version}</p></div>
          <div><p className="text-slate-500">Contact to use</p><p className="font-medium">{preparation.masked_phone ?? "No canonical phone"}</p></div>
          <div><p className="text-slate-500">Requested action</p><p className="font-medium">{preparation.requested_action}</p></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Screening questions</CardTitle>
          <p className="text-sm text-slate-500">Changes here apply only to this outreach.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setQuestions(editableQuestions(preparation.default_screening_questions))}>
              Reset to Job defaults
            </Button>
            <Button asChild type="button" variant="outline">
              <Link href={`/jobs/${preparation.job_id}`}>Edit Job defaults</Link>
            </Button>
          </div>
          <ScreeningQuestionEditor value={questions} onChange={setQuestions} disabled={confirmMutation.isPending} />
        </CardContent>
      </Card>

      {!preparation.can_prepare ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Add a canonical Candidate phone before preparing voice outreach.
        </div>
      ) : null}
      <Button
        disabled={!preparation.can_prepare || questions.length === 0 || confirmMutation.isPending}
        onClick={() => confirmMutation.mutate()}
      >
        {confirmMutation.isPending ? "Confirming…" : "Confirm ready for execution"}
      </Button>
    </div>
  );
}
