export const outreachKeys = {
  all: ["outreach"] as const,
  list(offset: number) {
    return [...this.all, "list", offset] as const;
  },
  preparation(jobCandidateId: string) {
    return [...this.all, "preparation", jobCandidateId] as const;
  },
  detail(outreachRequestId: string) {
    return [...this.all, "detail", outreachRequestId] as const;
  },
};
