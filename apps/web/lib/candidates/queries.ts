export const candidateKeys = {
  all: ["candidates"] as const,
  list: (query?: string) => ["candidates", "list", query?.trim() ?? ""] as const,
  detail: (candidateId: string) => ["candidates", candidateId] as const,
};
