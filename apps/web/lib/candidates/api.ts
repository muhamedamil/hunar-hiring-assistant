import { api } from "@/lib/api/client";
import type {
  Candidate,
  CandidateListResponse,
  CandidateProfileInput,
} from "@/lib/candidates/types";

export function listCandidates(query?: string) {
  const params = new URLSearchParams({ limit: "100", offset: "0" });
  if (query?.trim()) params.set("q", query.trim());
  return api.get<CandidateListResponse>(`/candidates?${params.toString()}`);
}

export function getCandidate(candidateId: string) {
  return api.get<Candidate>(`/candidates/${candidateId}`);
}

export function createCandidate(profile: CandidateProfileInput) {
  return api.post<Candidate>("/candidates", profile);
}

export function updateCandidate(
  candidateId: string,
  expectedRevision: number,
  profile: CandidateProfileInput,
) {
  return api.patch<Candidate>(`/candidates/${candidateId}`, {
    expected_revision: expectedRevision,
    profile,
  });
}
