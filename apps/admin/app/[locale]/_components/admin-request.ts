import { ApiError } from "@vergeo/config";

export type AdminRequestFailure =
  { kind: "permission"; message?: string } | { kind: "generic"; message?: string };

/** Map API client failures to admin UX states (permission-denied vs retryable error). */
export function classifyAdminRequestError(error: unknown): AdminRequestFailure {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403 || error.code === "forbidden") {
      return { kind: "permission", message: error.message };
    }
    return { kind: "generic", message: error.message };
  }
  return { kind: "generic" };
}
