import { assertEquals, assertThrows } from "jsr:@std/assert";
import { Webhook } from "https://esm.sh/standardwebhooks@1.0.0";
import { sendAtSms } from "./at_client.ts";
import { handleSendSmsOtp } from "./index.ts";
import { verifySendSmsHook } from "./hook.ts";

const HOOK_SECRET = "v1,whsec_dGhpcyBpcyBhIHZlcnlnZW81IHRlc3Qgc2VjcmV0IQ==";
const BASE64_SECRET = "dGhpcyBpcyBhIHZlcnlnZW81IHRlc3Qgc2VjcmV0IQ==";

const testEnv = {
  SEND_SMS_HOOK_SECRET: HOOK_SECRET,
  AT_API_KEY: "test-api-key",
  AT_USERNAME: "sandbox",
  AT_SENDER_ID: "VERGEO5",
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

Deno.test("handleSendSmsOtp sends OTP via Africa's Talking on valid hook", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify({ SMSMessageData: { Recipients: [] } }), {
      status: 201,
    });
  };

  const body = {
    user: { phone: "+260971000099" },
    sms: { otp: "654321" },
  };
  const { payload, headers } = signPayload(body);

  const response = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      headers,
      body: payload,
    }),
    { fetchImpl, env: testEnv },
  );

  assertEquals(response.status, 200);
  assertEquals(calls.length, 1);
  assertEquals(calls[0]?.url, "https://api.africastalking.com/version1/messaging");

  const init = calls[0]?.init;
  const requestHeaders = init?.headers as Record<string, string>;
  assertEquals(requestHeaders.apiKey, "test-api-key");

  const form = new URLSearchParams(String(init?.body));
  assertEquals(form.get("to"), "+260971000099");
  assertEquals(form.get("from"), "VERGEO5");
  assertEquals(form.get("username"), "sandbox");
  assertEquals(form.get("message"), "Your Vergeo5 code is 654321");
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

Deno.test("sendAtSms maps AT 4xx to permanent failure", async () => {
  const fetchImpl: typeof fetch = async () => new Response("InvalidPhoneNumber", { status: 400 });

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, false);
    assertEquals(result.status, 400);
  }
});

Deno.test("sendAtSms maps AT 5xx to retryable failure", async () => {
  const fetchImpl: typeof fetch = async () => new Response("upstream error", { status: 503 });

  const result = await sendAtSms(
    {
      to: "+260971000099",
      message: "test",
      from: "VERGEO5",
      username: "sandbox",
      apiKey: "key",
    },
    fetchImpl,
  );

  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.retryable, true);
    assertEquals(result.status, 503);
  }
});

Deno.test("handleSendSmsOtp returns 400 on AT 4xx and 500 on AT 5xx", async () => {
  const body = {
    user: { phone: "+260971000099" },
    sms: { otp: "111111" },
  };
  const { payload, headers } = signPayload(body);

  const permanent = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      headers,
      body: payload,
    }),
    {
      env: testEnv,
      fetchImpl: async () => new Response("bad request", { status: 422 }),
    },
  );
  assertEquals(permanent.status, 400);

  const retryable = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      headers,
      body: payload,
    }),
    {
      env: testEnv,
      fetchImpl: async () => new Response("server error", { status: 502 }),
    },
  );
  assertEquals(retryable.status, 500);
});
