import type { AtSendResult } from "./at_client.ts";

type FailedAtSendResult = Extract<AtSendResult, { ok: false }>;

export function buildPermanentHookFailure(result: FailedAtSendResult): Response {
  return new Response(
    JSON.stringify({
      error: {
        http_code: result.status,
        message: result.message,
        retryable: false,
      },
    }),
    { status: 400, headers: { "Content-Type": "application/json" } },
  );
}

export function buildRetryableHookFailure(result: FailedAtSendResult): Response {
  const headers = new Headers({ "Content-Type": "application/json" });
  // Supabase Auth retries 429/503 when a non-empty retry-after header is present.
  headers.set("retry-after", result.rateLimited ? "60" : "2");
  return new Response(
    JSON.stringify({
      error: {
        http_code: result.status,
        message: result.message,
        retryable: true,
      },
    }),
    {
      status: result.rateLimited ? 429 : 503,
      headers,
    },
  );
}
