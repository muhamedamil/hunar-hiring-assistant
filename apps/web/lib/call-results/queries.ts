export const callResultKeys = {
  detail: (executionId: string) => ["voice-call-result", executionId] as const,
};
