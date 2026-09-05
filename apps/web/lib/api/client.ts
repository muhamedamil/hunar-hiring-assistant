import { ApiError, isApiErrorEnvelope } from "@/lib/api/errors";
import { publicEnv } from "@/lib/env";

function createRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `web-${Date.now()}-${Math.random()}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", headers.get("X-Request-ID") ?? createRequestId());
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${publicEnv.apiBaseUrl}${path}`, {
      ...init,
      headers,
    });
  } catch (error) {
    throw new ApiError(0, "NETWORK_ERROR", "Unable to reach the API.", undefined, error);
  }

  const text = await response.text();
  const body: unknown = text ? safeJsonParse(text) : undefined;

  if (!response.ok) {
    if (isApiErrorEnvelope(body)) {
      throw new ApiError(
        response.status,
        body.error.code,
        body.error.message,
        body.error.request_id,
        body.error.details,
      );
    }
    throw new ApiError(
      response.status,
      "UNEXPECTED_API_ERROR",
      "The API returned an unexpected error response.",
      response.headers.get("X-Request-ID") ?? undefined,
    );
  }

  return body as T;
}

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

export const api = {
  get<T>(path: string, init?: RequestInit) {
    return request<T>(path, { ...init, method: "GET" });
  },

  post<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>(path, {
      ...init,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },

  patch<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>(path, {
      ...init,
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};
