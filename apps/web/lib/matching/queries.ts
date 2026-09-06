export const matchingKeys = {
  all: ["matching"] as const,
  job(jobId: string) {
    return [...this.all, "job", jobId] as const;
  },
  detail(jobCandidateId: string) {
    return [...this.all, "detail", jobCandidateId] as const;
  },
  matches(jobCandidateId: string) {
    return [...this.all, "matches", jobCandidateId] as const;
  },
};
