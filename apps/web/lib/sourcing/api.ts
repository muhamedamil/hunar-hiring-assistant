import { api } from "@/lib/api/client";
import type {
  SourcingEnrichment,
  SourcingRun,
  SourcingRunListResponse,
} from "@/lib/sourcing/types";

export function startSourcingRun(jobId: string, resultLimit: 10 | 25 | 50) {
  return api.post<SourcingRun>(`/jobs/${jobId}/sourcing-runs`, {
    result_limit: resultLimit,
  });
}

export function listSourcingRuns(jobId: string) {
  return api.get<SourcingRunListResponse>(`/jobs/${jobId}/sourcing-runs`);
}

export function getSourcingRun(runId: string) {
  return api.get<SourcingRun>(`/sourcing-runs/${runId}`);
}

export function retrySourcingRun(runId: string) {
  return api.post<SourcingRun>(`/sourcing-runs/${runId}/retry`);
}

export function enrichSourcingResult(resultId: string) {
  return api.post<SourcingEnrichment>(`/sourcing-results/${resultId}/enrich`);
}

export function getSourcingEnrichment(enrichmentId: string) {
  return api.get<SourcingEnrichment>(`/sourcing-enrichments/${enrichmentId}`);
}
