export {
  EMAIL_MASK,
  PHONE_MASK,
  REDACTED,
  SENSITIVE_KEY_PARTS,
  TOKEN_MASK,
  isSentryTestEndpointEnabled,
  keyIsSensitive,
  resolveEnvironment,
  resolveReleaseSha,
  scrub,
  scrubText,
} from "./scrub";
export {
  reportClientError,
  type ClientErrorApplication,
  type ClientErrorBoundary,
  type ClientErrorPayload,
  type ReportClientErrorOptions,
} from "./report-client-error";
export { useReportClientError } from "./use-report-client-error";
