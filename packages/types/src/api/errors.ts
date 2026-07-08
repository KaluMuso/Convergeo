/** Uniform API error envelope (matches FastAPI `build_error_envelope`). */
export type ApiErrorEnvelope = {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
  };
};
