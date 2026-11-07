import { parseAuthError } from "./auth-utils";

import type { AuthPortal } from "@vergeo/auth/portal";

export type AuthFailureStage = "initialize" | "authenticate" | "navigate";

/** Only fixed categories and an HTTP status may leave the error boundary.
 * Never return error messages, arbitrary provider codes, URLs or session data.
 */
export function describeAuthFailure(
  error: unknown,
  stage: AuthFailureStage,
  portal: AuthPortal,
  mode: "login" | "signup",
) {
  const parsed =
    stage === "initialize"
      ? { code: "client_unavailable" as const }
      : stage === "navigate"
        ? { code: "generic" as const }
        : parseAuthError(error);
  const status =
    error && typeof error === "object" ? (error as { status?: unknown }).status : undefined;
  const httpStatus =
    typeof status === "number" && Number.isInteger(status) && status >= 100 && status <= 599
      ? status
      : undefined;
  return {
    parsed,
    diagnostic: {
      stage,
      portal,
      mode,
      category: parsed.code,
      ...(httpStatus === undefined ? {} : { httpStatus }),
    },
  };
}
