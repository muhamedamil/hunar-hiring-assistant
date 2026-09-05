export type ApiErrorEnvelope = {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: unknown;
  };
};
