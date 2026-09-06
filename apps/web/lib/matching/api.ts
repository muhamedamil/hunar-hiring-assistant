import { api } from "@/lib/api/client";
import type {
  JobCandidateDetail,
  JobCandidateListResponse,
  MatchEvaluation,
  MatchHistoryResponse,
  ShortlistStatus,
} from "@/lib/matching/types";

export function listJobCandidates(
  jobId: string,
  shortlistStatus?: ShortlistStatus,
  limit = 20,
  offset = 0,
) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (shortlistStatus) params.set("shortlist_status", shortlistStatus);
  return api.get<JobCandidateListResponse>(`/jobs/${jobId}/job-candidates?${params.toString()}`);
}

export function getJobCandidate(jobCandidateId: string) {
  return api.get<JobCandidateDetail>(`/job-candidates/${jobCandidateId}`);
}

export function addManualJobCandidate(jobId: string, candidateId: string) {
  return api.post<JobCandidateDetail>(`/jobs/${jobId}/job-candidates`, {
    candidate_id: candidateId,
  });
}

export function addSourcedJobCandidate(resultId: string) {
  return api.post<JobCandidateDetail>(`/sourcing-results/${resultId}/job-candidate`);
}

export function evaluateJobCandidate(jobCandidateId: string) {
  return api.post<MatchEvaluation>(`/job-candidates/${jobCandidateId}/match`);
}

export function listJobCandidateMatches(jobCandidateId: string) {
  return api.get<MatchHistoryResponse>(`/job-candidates/${jobCandidateId}/matches?limit=20&offset=0`);
}

export function updateShortlist(
  jobCandidateId: string,
  expectedRevision: number,
  status: ShortlistStatus,
) {
  return api.patch<JobCandidateDetail>(`/job-candidates/${jobCandidateId}/shortlist`, {
    expected_revision: expectedRevision,
    status,
  });
}
