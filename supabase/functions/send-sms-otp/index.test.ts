import { assertEquals, assertThrows } from "jsr:@std/assert";
import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";
import { resolveAtEnvironment, resolveAtMessagingUrl } from "./at_config.ts";
import { classifyRecipientStatus, sendAtSms } from "./at_client.ts";
import { handleSendSmsOtp } from "./index.ts";
import { logSmsOtpEvent } from "./logging.ts";
import { formatPhoneForAt } from "./phone.ts";
import { verifySendSmsHook } from "./hook.ts";

const HOOK_SECRET = "v1,whsec_dGhpcyBpcyBhIHZlcnlnZW81IHRlc3Qgc2VjcmV0IQ==";
const BASE64_SECRET = "dGhpcyBpcyBhIHZlcnlnZW81IHRlc3Qgc2VjcmV0IQ==";

const testEnv = {
  SEND_SMS_HOOK_SECRET: HOOK_SECRET,
  AT_API_KEY: "test-api-key",
  AT_USERNAME: "sandbox",
  AT_SENDER_ID: "VERGEO5",
  AT_ENVIRONMENT: "sandbox",
};

function signPayload(body: Record<string, unknown>) {
  const payload = JSON.stringify(body);
  const wh = new Webhook(BASE64_SECRET);
  const msgId = crypto.randomUUID();
  const timestamp = new Date();
  const signature = wh.sign(msgId, timestamp, payload);
  return {
    payload,
    headers: {
      "webhook-id": msgId,
      "webhook-timestamp": String(Math.floor(timestamp.getTime() / 1000)),
      "webhook-signature": signature,
    },
  };
}

function atSuccessBody(statusCode: number, status = "Success") {
  return JSON.stringify({
    SMSMessageData: {
      Message: "Sent to 1/1 Total Cost: KES 0.8000",
      Recipients: [{ statusCode, status, number: "+260971000099", messageId: "ATXid_test" }],
    },
  });
}

function makeHookRequest(
  body: Record<string, unknown>,
  headers: Record<string, string>,
  fetchImpl?: typeof fetch,
  env: Record<string, string | undefined> = testEnv,
) {
  const { payload, headers: signedHeaders } = signPayload(body);
  return handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      headers: { ...signedHeaders, ...headers },
      body: payload,
    }),
    { fetchImpl, env },
  );
}

Deno.test("verifySendSmsHook accepts a valid signed payload", () => {
  const body = {
    user: { phone: "+260971000001" },
    sms: { otp: "123456" },
  };
  const { payload, headers } = signPayload(body);
  const verified = verifySendSmsHook(payload, headers, HOOK_SECRET);
  assertEquals(verified.user.phone, "+260971000001");
  assertEquals(verified.sms.otp, "123456");
});

Deno.test("verifySendSmsHook rejects a bad signature", () => {
  const body = {
    user: { phone: "+260971000001" },
    sms: { otp: "123456" },
  };
  const { payload, headers } = signPayload(body);
  headers["webhook-signature"] = "v1,invalid";

  assertThrows(() => verifySendSmsHook(payload, headers, HOOK_SECRET), Error);
});

Deno.test("resolveAtEnvironment accepts sandbox and live", () => {
  assertEquals(resolveAtEnvironment("sandbox"), "sandbox");
  assertEquals(resolveAtEnvironment("live"), "live");
  assertEquals(resolveAtEnvironment(" SANDBOX "), "sandbox");
});

Deno.test("resolveAtEnvironment rejects unknown values fail-closed", () => {
  assertThrows(() => resolveAtEnvironment("production"), Error, "sandbox or live");
  assertThrows(() => resolveAtEnvironment(""), Error, "missing");
  assertThrows(() => resolveAtEnvironment(undefined), Error, "missing");
});

Deno.test("resolveAtMessagingUrl maps sandbox and live endpoints", () => {
  assertEquals(
    resolveAtMessagingUrl("sandbox"),
    "https://api.sandbox.africastalking.com/version1/messaging",
  );
  assertEquals(resolveAtMessagingUrl("live"), "https://api.africastalking.com/version1/messaging");
});

Deno.test("formatPhoneForAt adds leading plus for canonical Auth storage", () => {
  assertEquals(formatPhoneForAt("260971000099"), "+260971000099");
  assertEquals(formatPhoneForAt("+260971000099"), "+260971000099");
});

Deno.test("formatPhoneForAt rejects malformed numbers fail-closed", () => {
  assertThrows(() => formatPhoneForAt(""), Error);
  assertThrows(() => formatPhoneForAt("260 971000099"), Error);
  assertThrows(() => formatPhoneForAt("+"), Error);
});

Deno.test("classifyRecipientStatus accepts 100/101/102", () => {
  for (const code of [100, 101, 102]) {
    assertEquals(classifyRecipientStatus(code), { ok: true, retryable: false });
  }
});

Deno.test("classifyRecipientStatus rejects permanent provider failures", () => {
  for (const code of [401, 402, 403, 405, 502]) {
    assertEquals(classifyRecipientStatus(code), { ok: false, retryable: false });
  }
});

Deno.test("handleSendSmsOtp sends OTP via Africa's Talking on valid hook", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(atSuccessBody(101), { status: 201 });
  };

  const response = await makeHookRequest(
    { user: { phone: "260971000099" }, sms: { otp: "654321" } },
    {},
    fetchImpl,
  );

  assertEquals(response.status, 200);
  assertEquals(await response.text(), "");
  assertEquals(calls.length, 1);
  assertEquals(calls[0]?.url, "https://api.sandbox.africastalking.com/version1/messaging");

  const init = calls[0]?.init;
  const requestHeaders = init?.headers as Record<string, string>;
  assertEquals(requestHeaders.apiKey, "test-api-key");

  const form = new URLSearchParams(String(init?.body));
  assertEquals(form.get("to"), "+260971000099");
  assertEquals(form.get("from"), "VERGEO5");
  assertEquals(form.get("username"), "sandbox");
  assertEquals(form.get("message"), "Your Vergeo5 code is 654321");
});

Deno.test("handleSendSmsOtp uses live endpoint when AT_ENVIRONMENT=live", async () => {
  const calls: Array<{ url: string }> = [];
  const fetchImpl: typeof fetch = async (input) => {
    calls.push({ url: String(input) });
    return new Response(atSuccessBody(102), { status: 201 });
  };

  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "111111" } },
    {},
    fetchImpl,
    { ...testEnv, AT_ENVIRONMENT: "live" },
  );

  assertEquals(response.status, 200);
  assertEquals(calls[0]?.url, "https://api.africastalking.com/version1/messaging");
});

Deno.test("handleSendSmsOtp rejects invalid hook signature", async () => {
  const body = {
    user: { phone: "+260971000099" },
    sms: { otp: "654321" },
  };
  const { payload, headers } = signPayload(body);
  headers["webhook-signature"] = "v1,badsignature";

  const response = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      headers,
      body: payload,
    }),
    { env: testEnv },
  );

  assertEquals(response.status, 401);
});

Deno.test("handleSendSmsOtp rejects missing hook secret", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
    {},
    undefined,
    { ...testEnv, SEND_SMS_HOOK_SECRET: undefined },
  );
  assertEquals(response.status, 401);
});

Deno.test("handleSendSmsOtp rejects missing AT credentials", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
    {},
    async () => new Response(atSuccessBody(101), { status: 201 }),
    { ...testEnv, AT_API_KEY: undefined },
  );
  assertEquals(response.status, 500);
});

Deno.test("handleSendSmsOtp rejects invalid AT environment", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
    {},
    async () => new Response(atSuccessBody(101), { status: 201 }),
    { ...testEnv, AT_ENVIRONMENT: "production" },
  );
  assertEquals(response.status, 500);
});

Deno.test("sendAtSms maps AT transport error to retryable failure", async () => {
  const fetchImpl: typeof fetch = async () => {
    throw new Error("network down");
  };

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
      environment: "sandbox",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, true);
    assertEquals(result.status, 502);
  }
});

Deno.test("sendAtSms maps AT HTTP 4xx to permanent failure", async () => {
  const fetchImpl: typeof fetch = async () => new Response("InvalidPhoneNumber", { status: 400 });

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
      environment: "sandbox",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, false);
    assertEquals(result.status, 400);
  }
});

Deno.test("sendAtSms maps AT HTTP 5xx to retryable failure", async () => {
  const fetchImpl: typeof fetch = async () => new Response("upstream error", { status: 503 });

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
      environment: "sandbox",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, true);
    assertEquals(result.status, 503);
  }
});

Deno.test("sendAtSms rejects malformed AT JSON fail-closed", async () => {
  const fetchImpl: typeof fetch = async () => new Response("not-json", { status: 201 });

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
      environment: "sandbox",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, false);
    assertEquals(result.message.includes("missing Recipients"), true);
  }
});

Deno.test("sendAtSms accepts HTTP 2xx recipient status codes 100/101/102", async () => {
  for (const code of [100, 101, 102]) {
    const result = await sendAtSms(
      {
        to: "+260971000099",
        message: "test",
        from: "VERGEO5",
        username: "sandbox",
        apiKey: "key",
        environment: "sandbox",
      },
      async () => new Response(atSuccessBody(code), { status: 201 }),
    );
    assertEquals(result.ok, true);
  }
});

Deno.test("sendAtSms rejects HTTP 2xx recipient failures", async () => {
  const cases = [
    { code: 401, status: "RiskHold" },
    { code: 402, status: "InvalidSenderId" },
    { code: 403, status: "InvalidPhoneNumber" },
    { code: 405, status: "InsufficientBalance" },
  ];

  for (const testCase of cases) {
    const result = await sendAtSms(
      {
        to: "+260971000099",
        message: "test",
        from: "VERGEO5",
        username: "sandbox",
        apiKey: "key",
        environment: "sandbox",
      },
      async () => new Response(atSuccessBody(testCase.code, testCase.status), { status: 201 }),
    );
    assertEquals(result.ok, false);
    if (!result.ok) {
      assertEquals(result.retryable, false);
      assertEquals(result.message.includes(String(testCase.code)), true);
    }
  }
});

Deno.test("sendAtSms rejects empty Recipients array", async () => {
  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
      environment: "sandbox",
    },
    async () =>
      new Response(JSON.stringify({ SMSMessageData: { Recipients: [] } }), { status: 201 }),
  );

  assertEquals(result.ok, false);
});

Deno.test("handleSendSmsOtp returns 400 on AT 4xx and 503+retry-after on AT 5xx", async () => {
  const body = {
    user: { phone: "+260971000099" },
    sms: { otp: "111111" },
  };

  const permanent = await makeHookRequest(
    body,
    {},
    async () =>
      new Response("bad request", {
        status: 422,
      }),
  );
  assertEquals(permanent.status, 400);
  assertEquals(permanent.headers.get("retry-after"), null);

  const retryable = await makeHookRequest(
    body,
    {},
    async () =>
      new Response("server error", {
        status: 502,
      }),
  );
  assertEquals(retryable.status, 503);
  assertEquals(retryable.headers.get("retry-after"), "2");
});

Deno.test("handleSendSmsOtp returns 429+retry-after on AT rate limiting", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "111111" } },
    {},
    async () => new Response("rate limited", { status: 429 }),
  );
  assertEquals(response.status, 429);
  assertEquals(response.headers.get("retry-after"), "60");
});

Deno.test("handleSendSmsOtp returns 503+retry-after on transport failure", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "111111" } },
    {},
    async () => {
      throw new Error("network down");
    },
  );
  assertEquals(response.status, 503);
  assertEquals(response.headers.get("retry-after"), "2");
});

Deno.test("handleSendSmsOtp returns 400 when AT accepts HTTP but rejects recipient", async () => {
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "111111" } },
    {},
    async () => new Response(atSuccessBody(403, "InvalidPhoneNumber"), { status: 201 }),
  );
  assertEquals(response.status, 400);
});

Deno.test("diagnostic logs never include secret or OTP values", () => {
  const lines: string[] = [];
  const originalLog = console.log;
  console.log = (message: string) => {
    lines.push(message);
  };

  try {
    logSmsOtpEvent("at_recipient_accepted", {
      at_environment: "sandbox",
      at_http_status: 201,
      recipient_status_code: 101,
      recipient_status: "Success",
      retryable: false,
      provider_outcome: "accepted",
      phone_tail: "***0099",
    });
  } finally {
    console.log = originalLog;
  }

  const serialized = lines.join("\n");
  assertEquals(serialized.includes("654321"), false);
  assertEquals(serialized.includes("test-api-key"), false);
  assertEquals(serialized.includes(HOOK_SECRET), false);
  assertEquals(serialized.includes("whsec_"), false);
  assertEquals(serialized.includes("+260971000099"), false);
  assertEquals(serialized.includes("***0099"), true);
});
