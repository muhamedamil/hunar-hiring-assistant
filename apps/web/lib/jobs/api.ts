import { api } from "@/lib/api/client";
import type {
  Job,
  JobAnalysisProposal,
  JobDefinitionInput,
  JobListResponse,
  JobStatus,
} from "@/lib/jobs/types";

export function listJobs(status?: JobStatus) {
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  if (status) params.set("status", status);
  return api.get<JobListResponse>(`/jobs?${params.toString()}`);
}

export function getJob(jobId: string) {
  return api.get<Job>(`/jobs/${jobId}`);
}

export function analyzeJob(input: { title?: string; description: string }) {
  return api.post<JobAnalysisProposal>("/jobs/analyze", input);
}

export function createJob(definition: Omit<JobDefinitionInput, "screening_questions"> & {
  screening_questions: Array<Omit<JobDefinitionInput["screening_questions"][number], "id">>;
}) {
  return api.post<Job>("/jobs", definition);
}

export function saveJobDraft(jobId: string, expectedRevision: number, definition: JobDefinitionInput) {
  return api.patch<Job>(`/jobs/${jobId}`, {
    expected_revision: expectedRevision,
    definition,
  });
}

export function markJobReady(jobId: string, expectedRevision: number, definition: JobDefinitionInput) {
  return api.post<Job>(`/jobs/${jobId}/ready`, {
    expected_revision: expectedRevision,
    definition,
  });
}

export function reopenJob(jobId: string, expectedRevision: number) {
  return api.post<Job>(`/jobs/${jobId}/reopen`, { expected_revision: expectedRevision });
}
