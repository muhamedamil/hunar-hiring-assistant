import type { ApiErrorEnvelope } from "@/lib/api/types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== "object") return false;
  const maybe = value as Partial<ApiErrorEnvelope>;
  return Boolean(
    maybe.error &&
      typeof maybe.error.code === "string" &&
      typeof maybe.error.message === "string" &&
      typeof maybe.error.request_id === "string",
  );
}
