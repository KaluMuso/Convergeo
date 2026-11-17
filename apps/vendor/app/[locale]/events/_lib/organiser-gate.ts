import { ApiError } from "@vergeo/config";

/**
 * True when the events API refused the caller because they are not (yet) an
 * eligible organiser: no vendor profile (`forbidden`) or ID not verified
 * (`kyc_required`). Both are expected states, not load failures.
 */
export function isNotOrganiserError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 403 &&
    (error.code === "kyc_required" || error.code === "forbidden")
  );
}
