import { api } from "@/lib/api/client";
import type {
  OutreachListResponse,
  OutreachPreparation,
  OutreachRequest,
  PrepareOutreachInput,
} from "@/lib/outreach/types";

export function getOutreachPreparation(jobCandidateId: string): Promise<OutreachPreparation> {
  return api.get(`/job-candidates/${jobCandidateId}/outreach-preparation`);
}

export function prepareOutreach(
  jobCandidateId: string,
  input: PrepareOutreachInput,
): Promise<OutreachRequest> {
  return api.post(`/job-candidates/${jobCandidateId}/outreach-requests`, input);
}

export function getOutreachRequest(outreachRequestId: string): Promise<OutreachRequest> {
  return api.get(`/outreach-requests/${outreachRequestId}`);
}

export function listOutreachRequests(
  limit = 20,
  offset = 0,
): Promise<OutreachListResponse> {
  return api.get(`/outreach-requests?limit=${limit}&offset=${offset}`);
}
