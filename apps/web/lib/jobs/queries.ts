export const jobKeys = {
  all: ["jobs"] as const,
  detail: (jobId: string) => ["jobs", jobId] as const,
};
