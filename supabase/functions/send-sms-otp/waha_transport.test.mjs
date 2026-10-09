import { test } from "node:test";
import assert from "node:assert/strict";
import { selectOtpTransport, sendWahaOtp, validateWahaPayload } from "./waha_transport.ts";

const env = {
  SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  SMS_OTP_TRANSPORT: "waha",
  WAHA_OTP_ENABLED: "true",
  WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.staging.vergeo5.com/webhook/convergeo-auth-otp-draft",
  WAHA_OTP_N8N_AUTH_TOKEN: "a".repeat(32),
  WAHA_OTP_N8N_HMAC_SECRET: "b".repeat(32),
};
const now = 1_800_000_000_000;
const payload = { user: { phone: "260971000099" }, sms: { otp: "654321" } };
const headers = new Headers({
  "webhook-id": "request_12345678",
  "webhook-timestamp": String(now / 1000),
});

test("WAHA is default off and requires both switches", () => {
  assert.equal(selectOtpTransport({}), "at");
  assert.equal(selectOtpTransport({ SUPABASE_URL: env.SUPABASE_URL }), "disabled");
  assert.equal(selectOtpTransport({ ...env, WAHA_OTP_ENABLED: undefined }), "disabled");
  assert.equal(selectOtpTransport({ ...env, WAHA_OTP_ENABLED: "TRUE" }), "disabled");
  assert.equal(selectOtpTransport(env), "waha");
  assert.equal(
    selectOtpTransport({
      ...env,
      SUPABASE_URL: "https://dpadrlxukcjbewpqympu.supabase.co",
    }),
    "disabled",
  );
  assert.equal(selectOtpTransport({ ...env, SMS_OTP_TRANSPORT: "at" }), "disabled");
  assert.equal(
    selectOtpTransport({
      ...env,
      SMS_OTP_TRANSPORT: "at",
      AT_ENVIRONMENT: "live",
    }),
    "disabled",
  );
  assert.equal(
    selectOtpTransport({
      ...env,
      SMS_OTP_TRANSPORT: "at",
      AT_ENVIRONMENT: "sandbox",
    }),
    "at",
  );
  assert.equal(selectOtpTransport({ SMS_OTP_TRANSPORT: "unknown" }), "invalid");
});

test("only bounded individual phone and numeric code cross the handoff", () => {
  assert.deepEqual(validateWahaPayload(payload), {
    phone: "+260971000099",
    otp: "654321",
  });
  for (const phone of [
    "260 971000099",
    "260971000099@g.us",
    "@c.us",
    "+260971000099\n",
    "1".repeat(30),
  ]) {
    assert.equal(validateWahaPayload({ user: { phone }, sms: { otp: "654321" } }), undefined);
  }
  for (const otp of ["", "123", "123456789", "12 456", "a23456"]) {
    assert.equal(
      validateWahaPayload({ user: { phone: "+260971000099" }, sms: { otp } }),
      undefined,
    );
  }
});

test("signed handoff has a bounded deadline, correct recipient and authenticated receipt", async () => {
  let count = 0;
  const result = await sendWahaOtp(
    payload,
    headers,
    env,
    async (url, init) => {
      count++;
      assert.equal(url, env.WAHA_OTP_N8N_WEBHOOK_URL);
      assert.equal(init.redirect, "error");
      assert.equal(init.headers["X-Convergeo-OTP-Auth"], env.WAHA_OTP_N8N_AUTH_TOKEN);
      const body = JSON.parse(init.body);
      assert.equal(body.phone, "+260971000099");
      assert.equal(body.otp, "654321");
      assert.equal(body.requestId, "request_12345678");
      assert.ok(body.deadline <= now + 4000);
      const input = `v1\n${body.timestamp}\n${body.requestId}\n${body.deadline}\n${body.phone}\n${body.otp}`;
      const key = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(env.WAHA_OTP_N8N_HMAC_SECRET),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"],
      );
      const expected = Buffer.from(
        await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(input)),
      ).toString("hex");
      assert.equal(init.headers["X-Convergeo-OTP-Signature"], expected);
      return new Response(JSON.stringify({ accepted: true, requestId: body.requestId }), {
        status: 200,
      });
    },
    now,
  );
  assert.deepEqual(result, { ok: true });
  assert.equal(count, 1);
});

test("missing, malformed and stale source identity never invoke n8n", async () => {
  let count = 0;
  const fetchMock = async () => {
    count++;
    throw Error("must not send");
  };
  for (const h of [
    new Headers(),
    new Headers({
      "webhook-id": "bad",
      "webhook-timestamp": String(now / 1000),
    }),
    new Headers({
      "webhook-id": "request_12345678",
      "webhook-timestamp": String((now - 31_000) / 1000),
    }),
  ]) {
    assert.deepEqual(await sendWahaOtp(payload, h, env, fetchMock, now), {
      ok: false,
      status: 400,
    });
  }
  assert.equal(count, 0);
});

test("missing authentication or insecure URL fails closed", async () => {
  let count = 0;
  const fetchMock = async () => {
    count++;
    throw Error("must not send");
  };
  assert.deepEqual(
    await sendWahaOtp(
      payload,
      headers,
      { ...env, WAHA_OTP_N8N_HMAC_SECRET: undefined },
      fetchMock,
      now,
    ),
    { ok: false, status: 500 },
  );
  assert.deepEqual(
    await sendWahaOtp(
      payload,
      headers,
      { ...env, WAHA_OTP_N8N_WEBHOOK_URL: "http://n8n.test/webhook/otp" },
      fetchMock,
      now,
    ),
    { ok: false, status: 500 },
  );
  assert.deepEqual(
    await sendWahaOtp(
      payload,
      headers,
      {
        ...env,
        WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.vergeo5.com/webhook/convergeo-auth-otp-draft",
      },
      fetchMock,
      now,
    ),
    { ok: false, status: 500 },
  );
  assert.deepEqual(
    await sendWahaOtp(
      payload,
      headers,
      {
        ...env,
        WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.staging.vergeo5.com/webhook/other",
      },
      fetchMock,
      now,
    ),
    { ok: false, status: 500 },
  );
  assert.equal(count, 0);
});

test("offline, provider error, timeout and uncertain receipt fail closed without retry or body disclosure", async () => {
  let count = 0;
  const outcomes = [
    async () => {
      throw Error("secret 654321 +260971000099 provider offline");
    },
    async () => new Response("secret 654321 provider error", { status: 503 }),
    async () =>
      new Response(JSON.stringify({ accepted: true, requestId: "wrong" }), {
        status: 200,
      }),
    async () =>
      new Response(
        JSON.stringify({
          accepted: true,
          requestId: "request_12345678",
          leaked: true,
        }),
        { status: 200 },
      ),
  ];
  for (const outcome of outcomes) {
    const result = await sendWahaOtp(
      payload,
      headers,
      env,
      async () => {
        count++;
        return outcome();
      },
      now,
    );
    assert.deepEqual(result, { ok: false, status: 503 });
    assert.equal(JSON.stringify(result).includes("654321"), false);
    assert.equal(JSON.stringify(result).includes("+260971000099"), false);
  }
  assert.equal(count, outcomes.length);
});

test("a hung handoff is aborted once and never retried", async () => {
  let count = 0;
  const result = await sendWahaOtp(
    payload,
    headers,
    env,
    async (_url, init) => {
      count++;
      return await new Promise((_resolve, reject) => {
        init.signal.addEventListener(
          "abort",
          () => reject(new Error("secret provider timeout 654321")),
          { once: true },
        );
      });
    },
    now,
  );
  assert.deepEqual(result, { ok: false, status: 503 });
  assert.equal(count, 1);
});

test("provider exceptions and bodies cannot reach logs or returned result", async () => {
  const logs = [];
  const previousLog = console.log;
  const previousError = console.error;
  console.log = (...parts) => logs.push(parts.join(" "));
  console.error = (...parts) => logs.push(parts.join(" "));
  try {
    const result = await sendWahaOtp(
      payload,
      headers,
      env,
      async () => new Response("offline 654321 +260971000099", { status: 503 }),
      now,
    );
    assert.deepEqual(result, { ok: false, status: 503 });
    assert.equal(logs.join(" ").includes("654321"), false);
    assert.equal(logs.join(" ").includes("+260971000099"), false);
  } finally {
    console.log = previousLog;
    console.error = previousError;
  }
});
