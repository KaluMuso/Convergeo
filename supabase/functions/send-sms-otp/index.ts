import { resolveAtClientConfig, sendAtSms } from "./at_client.ts";
import { buildOtpMessage, verifySendSmsHook } from "./hook.ts";
import { logSmsOtpEvent } from "./logging.ts";
import { formatPhoneForAt } from "./phone.ts";

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
    logSmsOtpEvent("hook_signature_rejected", {
      provider_outcome: "invalid_signature",
    });
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
    logSmsOtpEvent("at_credentials_missing", {
      provider_outcome: "missing_at_credentials",
    });
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

  let atEnvironment;
  try {
    ({ environment: atEnvironment } = resolveAtClientConfig(env));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logSmsOtpEvent("at_environment_invalid", {
      provider_outcome: "invalid_at_environment",
    });
    return new Response(
      JSON.stringify({
        error: {
          http_code: 500,
          message,
        },
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  let to: string;
  try {
    to = formatPhoneForAt(hookPayload.user.phone);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logSmsOtpEvent("phone_format_rejected", {
      at_environment: atEnvironment,
      provider_outcome: "invalid_phone",
    });
    return new Response(
      JSON.stringify({
        error: {
          http_code: 400,
          message: `Invalid phone number: ${message}`,
        },
      }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  const result = await sendAtSms(
    {
      to,
      message: buildOtpMessage(hookPayload.sms.otp),
      from: senderId,
      username,
      apiKey,
      environment: atEnvironment,
    },
    deps.fetchImpl ?? fetch,
  );

  if (result.ok) {
    return new Response(null, { status: 200 });
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
