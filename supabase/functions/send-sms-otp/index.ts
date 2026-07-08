import { sendAtSms } from "./at_client.ts";
import { buildOtpMessage, verifySendSmsHook } from "./hook.ts";

type HandlerDeps = {
  fetchImpl?: typeof fetch;
  env?: Record<string, string | undefined>;
};

function readEnv(key: string, env: Record<string, string | undefined>): string | undefined {
  return env[key] ?? Deno.env.get(key);
}

export async function handleSendSmsOtp(req: Request, deps: HandlerDeps = {}): Promise<Response> {
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  const env = deps.env ?? Deno.env.toObject();
  const payload = await req.text();
  const headers = Object.fromEntries(req.headers);

  let hookPayload;
  try {
    const hookSecret = readEnv("SEND_SMS_HOOK_SECRET", env);
    if (!hookSecret) {
      throw new Error("SEND_SMS_HOOK_SECRET is not configured");
    }
    hookPayload = verifySendSmsHook(payload, headers, hookSecret);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return new Response(
      JSON.stringify({
        error: { http_code: 401, message: `Invalid hook signature: ${message}` },
      }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
  }

  const apiKey = readEnv("AT_API_KEY", env);
  const username = readEnv("AT_USERNAME", env);
  const senderId = readEnv("AT_SENDER_ID", env);

  if (!apiKey || !username || !senderId) {
    return new Response(
      JSON.stringify({
        error: {
          http_code: 500,
          message: "Africa's Talking credentials are not configured",
        },
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  const result = await sendAtSms(
    {
      to: hookPayload.user.phone,
      message: buildOtpMessage(hookPayload.sms.otp),
      from: senderId,
      username,
      apiKey,
    },
    deps.fetchImpl ?? fetch,
  );

  if (result.ok) {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const status = result.retryable ? 500 : 400;
  return new Response(
    JSON.stringify({
      error: {
        http_code: result.status,
        message: result.message,
        retryable: result.retryable,
      },
    }),
    { status, headers: { "Content-Type": "application/json" } },
  );
}

if (import.meta.main) {
  Deno.serve((req) => handleSendSmsOtp(req));
}
