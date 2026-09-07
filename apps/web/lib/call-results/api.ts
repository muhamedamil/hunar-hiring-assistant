import { api } from "@/lib/api/client";
import type { ReconciliationResult, VoiceCallResult } from "@/lib/call-results/types";

export function getCallResult(executionId: string): Promise<VoiceCallResult | null> {
  return api.get(`/voice-call-executions/${executionId}/screening-result`);
}

export function reconcileCallResult(executionId: string): Promise<ReconciliationResult> {
  return api.post(`/voice-call-executions/${executionId}/screening-result/reconcile`);
}
