"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { JobDescriptionSection } from "@/components/jobs/job-description-section";
import { JobStatusBadge } from "@/components/jobs/job-status-badge";
import {
  ScreeningQuestionEditor,
  type EditableQuestion,
} from "@/components/jobs/screening-question-editor";
import { RequirementsEditor } from "@/components/jobs/requirements-editor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import {
  analyzeJob,
  createJob,
  markJobReady,
  reopenJob,
  saveJobDraft,
} from "@/lib/jobs/api";
import { jobKeys } from "@/lib/jobs/queries";
import {
  emptyRequirements,
  type Job,
  type JobAnalysisProposal,
  type JobDefinitionInput,
  type JobRequirements,
} from "@/lib/jobs/types";

interface EditorState {
  title: string;
  companyName: string;
  description: string;
  requirements: JobRequirements;
  questions: EditableQuestion[];
}

function questionClientKey(id?: string) {
  return id ?? globalThis.crypto?.randomUUID?.() ?? `question-${Date.now()}-${Math.random()}`;
}

function stateFromJob(job?: Job): EditorState {
  if (!job) {
    return {
      title: "",
      companyName: "",
      description: "",
      requirements: { ...emptyRequirements },
      questions: [],
    };
  }
  return {
    title: job.title,
    companyName: job.company_name ?? "",
    description: job.description,
    requirements: job.requirements,
    questions: job.screening_questions.map((question) => ({
      ...question,
      client_key: questionClientKey(question.id),
    })),
  };
}

function toDefinition(state: EditorState): JobDefinitionInput {
  return {
    title: state.title.trim(),
    company_name: state.companyName.trim() || null,
    description: state.description.trim(),
    requirements: state.requirements,
    screening_questions: state.questions.map((question) => ({
      id: question.id,
      key: question.key.trim().toLowerCase(),
      prompt: question.prompt.trim(),
      answer_type: question.answer_type,
      required: question.required,
      options: question.options.map((option) => option.trim()).filter(Boolean),
    })),
  };
}


function mergeStrings(current: string[], suggested: string[]): string[] {
  const result = [...current];
  const seen = new Set(current.map((value) => value.trim().toLowerCase()));
  for (const value of suggested) {
    const key = value.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

function mergeRequirements(current: JobRequirements, suggested: JobRequirements): JobRequirements {
  const requiredSkills = mergeStrings(current.required_skills, suggested.required_skills);
  const requiredKeys = new Set(requiredSkills.map((value) => value.toLowerCase()));
  const preferredSkills = mergeStrings(current.preferred_skills, suggested.preferred_skills).filter(
    (value) => !requiredKeys.has(value.toLowerCase()),
  );
  return {
    alternate_titles: mergeStrings(current.alternate_titles, suggested.alternate_titles),
    required_skills: requiredSkills,
    preferred_skills: preferredSkills,
    locations: mergeStrings(current.locations, suggested.locations),
    min_years_experience: current.min_years_experience ?? suggested.min_years_experience,
    seniority: Array.from(new Set([...current.seniority, ...suggested.seniority])),
    employment_type: current.employment_type ?? suggested.employment_type,
    work_arrangement: current.work_arrangement ?? suggested.work_arrangement,
  };
}

function hasUsableSuggestions(proposal: JobAnalysisProposal): boolean {
  const requirements = proposal.requirements;
  return Boolean(
    requirements.alternate_titles.length ||
      requirements.required_skills.length ||
      requirements.preferred_skills.length ||
      requirements.locations.length ||
      requirements.min_years_experience !== null ||
      requirements.seniority.length ||
      requirements.employment_type !== null ||
      requirements.work_arrangement !== null ||
      proposal.suggested_screening_questions.length,
  );
}

function validateDefinition(state: EditorState, ready: boolean): string | null {
  if (!state.title.trim()) return "Enter a job title.";
  if (state.description.trim().length < 20) return "Job description must contain at least 20 characters.";

  const required = new Set(state.requirements.required_skills.map((skill) => skill.toLowerCase()));
  if (state.requirements.preferred_skills.some((skill) => required.has(skill.toLowerCase()))) {
    return "A skill cannot be both required and preferred.";
  }

  const keys = new Set<string>();
  const keyPattern = /^[a-z][a-z0-9_]{1,39}$/;
  for (const question of state.questions) {
    const key = question.key.trim().toLowerCase();
    if (!keyPattern.test(key)) return "Every screening question needs a valid snake_case result key.";
    if (keys.has(key)) return `Screening question key '${key}' is duplicated.`;
    keys.add(key);
    if (question.prompt.trim().length < 5) return "Every screening question needs a complete prompt.";
    if (question.answer_type === "choice") {
      const uniqueOptions = new Set(
        question.options.map((option) => option.trim().toLowerCase()).filter(Boolean),
      );
      if (uniqueOptions.size < 2) return "Choice questions need at least two unique options.";
    }
  }
  if (ready && state.questions.length === 0) return "Add at least one screening question before marking the job ready.";
  return null;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function JobEditor({ initialJob }: { initialJob?: Job }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [job, setJob] = useState<Job | undefined>(initialJob);
  const [state, setState] = useState<EditorState>(() => stateFromJob(initialJob));
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isReady = job?.status === "ready";

  function syncFromServer(nextJob: Job) {
    setJob(nextJob);
    setState(stateFromJob(nextJob));
    setError(null);
    void queryClient.invalidateQueries({ queryKey: jobKeys.all });
    void queryClient.setQueryData(jobKeys.detail(nextJob.id), nextJob);
  }

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeJob({ title: state.title.trim() || undefined, description: state.description }),
    onSuccess: (proposal) => {
      if (!hasUsableSuggestions(proposal)) {
        setFeedback(null);
        setError(
          "AI analysis completed but returned no usable requirements or screening questions. Try again or continue editing manually.",
        );
        return;
      }
      setState((current) => {
        const existingKeys = new Set(current.questions.map((question) => question.key.trim().toLowerCase()));
        const suggestedQuestions = proposal.suggested_screening_questions
          .filter((question) => !existingKeys.has(question.key.toLowerCase()))
          .map((question) => ({ ...question, client_key: questionClientKey() }));
        return {
          ...current,
          title: current.title.trim() || proposal.suggested_title || current.title,
          requirements: mergeRequirements(current.requirements, proposal.requirements),
          questions: [...current.questions, ...suggestedQuestions].slice(0, 10),
        };
      });
      setError(null);
      setFeedback("AI suggestions added. Review them before saving or marking the job ready.");
    },
    onError: (mutationError) => {
      setFeedback(null);
      setError(`${errorMessage(mutationError)} Manual editing is still available.`);
    },
  });

  const createMutation = useMutation({ mutationFn: createJob });
  const saveMutation = useMutation({
    mutationFn: ({ jobId, revision, definition }: { jobId: string; revision: number; definition: JobDefinitionInput }) =>
      saveJobDraft(jobId, revision, definition),
  });
  const readyMutation = useMutation({
    mutationFn: ({ jobId, revision, definition }: { jobId: string; revision: number; definition: JobDefinitionInput }) =>
      markJobReady(jobId, revision, definition),
  });
  const reopenMutation = useMutation({
    mutationFn: ({ jobId, revision }: { jobId: string; revision: number }) => reopenJob(jobId, revision),
  });

  const pending =
    analyzeMutation.isPending ||
    createMutation.isPending ||
    saveMutation.isPending ||
    readyMutation.isPending ||
    reopenMutation.isPending;

  async function ensureCreated(): Promise<Job> {
    if (job) return job;
    const definition = toDefinition(state);
    const created = await createMutation.mutateAsync({
      ...definition,
      screening_questions: definition.screening_questions.map((question) => ({
        key: question.key,
        prompt: question.prompt,
        answer_type: question.answer_type,
        required: question.required,
        options: question.options,
      })),
    });
    syncFromServer(created);
    return created;
  }

  async function handleSaveDraft() {
    const validation = validateDefinition(state, false);
    if (validation) {
      setError(validation);
      setFeedback(null);
      return;
    }
    setError(null);
    try {
      if (!job) {
        const created = await ensureCreated();
        setFeedback("Draft saved.");
        router.replace(`/jobs/${created.id}`);
        return;
      }
      const saved = await saveMutation.mutateAsync({
        jobId: job.id,
        revision: job.revision,
        definition: toDefinition(state),
      });
      syncFromServer(saved);
      setFeedback("Draft saved.");
    } catch (mutationError) {
      setFeedback(null);
      setError(errorMessage(mutationError));
    }
  }

  async function handleMarkReady() {
    const validation = validateDefinition(state, true);
    if (validation) {
      setError(validation);
      setFeedback(null);
      return;
    }
    setError(null);
    try {
      let currentJob = job;
      let definition = toDefinition(state);
      if (!currentJob) {
        currentJob = await ensureCreated();
        const idsByKey = new Map(
          currentJob.screening_questions.map((question) => [question.key, question.id]),
        );
        definition = {
          ...definition,
          screening_questions: definition.screening_questions.map((question) => ({
            ...question,
            id: idsByKey.get(question.key),
          })),
        };
      }
      const ready = await readyMutation.mutateAsync({
        jobId: currentJob.id,
        revision: currentJob.revision,
        definition,
      });
      syncFromServer(ready);
      setFeedback(`Job is ready at approved definition v${ready.approved_version}.`);
      router.replace(`/jobs/${ready.id}`);
    } catch (mutationError) {
      setFeedback(null);
      setError(errorMessage(mutationError));
    }
  }

  async function handleReopen() {
    if (!job) return;
    setError(null);
    try {
      const reopened = await reopenMutation.mutateAsync({ jobId: job.id, revision: job.revision });
      syncFromServer(reopened);
      setFeedback("Job reopened. New downstream work should remain blocked until you mark it ready again.");
    } catch (mutationError) {
      setFeedback(null);
      setError(errorMessage(mutationError));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            {job ? <JobStatusBadge status={job.status} version={job.approved_version} /> : null}
            {job ? <span className="text-xs text-slate-500">revision {job.revision}</span> : null}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">{job ? job.title : "Create job"}</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Build one approved hiring definition that both candidate sourcing and voice screening will consume.
          </p>
        </div>
        {isReady && job ? (
          <div className="flex flex-wrap gap-2">
            <Button asChild type="button">
              <Link href={`/jobs/${job.id}/sourcing`}>Find people</Link>
            </Button>
            <Button type="button" variant="outline" disabled={pending} onClick={handleReopen}>
              Reopen to edit
            </Button>
          </div>
        ) : null}
      </div>

      {feedback ? <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{feedback}</div> : null}
      {error ? <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</div> : null}

      <Card>
        <CardHeader>
          <CardTitle>Job definition</CardTitle>
        </CardHeader>
        <CardContent>
          <JobDescriptionSection
            title={state.title}
            companyName={state.companyName}
            description={state.description}
            disabled={Boolean(isReady)}
            analyzing={analyzeMutation.isPending}
            onTitleChange={(title) => setState((current) => ({ ...current, title }))}
            onCompanyNameChange={(companyName) => setState((current) => ({ ...current, companyName }))}
            onDescriptionChange={(description) => setState((current) => ({ ...current, description }))}
            onAnalyze={() => analyzeMutation.mutate()}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Requirements</CardTitle>
        </CardHeader>
        <CardContent>
          <RequirementsEditor
            value={state.requirements}
            disabled={Boolean(isReady)}
            onChange={(requirements) => setState((current) => ({ ...current, requirements }))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Screening questions</CardTitle>
        </CardHeader>
        <CardContent>
          <ScreeningQuestionEditor
            value={state.questions}
            disabled={Boolean(isReady)}
            onChange={(questions) => setState((current) => ({ ...current, questions }))}
          />
        </CardContent>
      </Card>

      {!isReady ? (
        <div className="sticky bottom-4 flex justify-end gap-3 rounded-xl border bg-white/95 p-4 shadow-lg backdrop-blur">
          <Button type="button" variant="outline" disabled={pending} onClick={handleSaveDraft}>
            {saveMutation.isPending || createMutation.isPending ? "Saving…" : "Save draft"}
          </Button>
          <Button type="button" disabled={pending} onClick={handleMarkReady}>
            {readyMutation.isPending ? "Marking ready…" : "Mark ready"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
