import { classifyAdminRequestError } from "./admin-request";

export type QueueLoadFailure = {
  permissionDenied: boolean;
  messageKey: "permissionDenied" | "error";
};

/**
 * Map a queue/detail fetch failure to the admin UX states used by
 * Dashboard / DuplicateQueue: permission-denied vs retryable error.
 */
export function resolveQueueLoadFailure(error: unknown): QueueLoadFailure {
  const classified = classifyAdminRequestError(error);
  if (classified.kind === "permission") {
    return { permissionDenied: true, messageKey: "permissionDenied" };
  }
  return { permissionDenied: false, messageKey: "error" };
}
