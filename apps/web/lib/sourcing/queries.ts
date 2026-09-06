export const sourcingKeys = {
  all: ["sourcing"] as const,
  jobRuns(jobId: string) {
    return [...this.all, "job", jobId] as const;
  },
  run(runId: string) {
    return [...this.all, "run", runId] as const;
  },
};
