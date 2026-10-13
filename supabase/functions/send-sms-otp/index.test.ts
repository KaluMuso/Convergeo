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
  SMS_OTP_TRANSPORT: "at",
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
      Recipients: [
        {
          statusCode,
          status,
          number: "+260971000099",
          messageId: "ATXid_test",
        },
      ],
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
    assertEquals(classifyRecipientStatus(code), {
      ok: false,
      retryable: false,
    });
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

Deno.test(
  "WAHA acceptance returns a JSON 200 hook response only after an exact receipt",
  async () => {
    const wahaEnv = {
      SEND_SMS_HOOK_SECRET: HOOK_SECRET,
      SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
      SMS_OTP_TRANSPORT: "waha",
      WAHA_OTP_ENABLED: "true",
      WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.vergeo5.com/webhook/convergeo-auth-otp-draft",
      WAHA_OTP_N8N_AUTH_TOKEN: "a".repeat(32),
      WAHA_OTP_N8N_HMAC_SECRET: "b".repeat(32),
    };
    const hookBody = { user: { phone: "+260971000099" }, sms: { otp: "654321" } };
    let sends = 0;
    const accepted = await makeHookRequest(
      hookBody,
      {},
      async (_input, init) => {
        sends++;
        const request = JSON.parse(String(init?.body));
        return new Response(JSON.stringify({ accepted: true, requestId: request.requestId }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
      wahaEnv,
    );
    assertEquals(accepted.status, 200);
    assertEquals(accepted.headers.get("content-type"), "application/json");
    assertEquals(await accepted.text(), "{}");
    assertEquals(sends, 1);

    const rejected = await makeHookRequest(
      hookBody,
      {},
      async () => {
        sends++;
        return new Response(JSON.stringify({ accepted: true, requestId: "wrong" }), {
          status: 200,
        });
      },
      wahaEnv,
    );
    assertEquals(rejected.status, 503);
    assertEquals(rejected.headers.get("content-type"), "application/json");
    assertEquals(JSON.parse(await rejected.text()), {
      error: { http_code: 503, message: "OTP delivery unavailable" },
    });
    assertEquals(sends, 2);
  },
);

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

Deno.test(
  "staging OTP defaults to disabled and refuses live AT before provider fetch",
  async () => {
    let calls = 0;
    const fetchImpl: typeof fetch = async () => {
      calls++;
      throw new Error("provider must not be called");
    };
    const staging = {
      ...testEnv,
      SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
      SMS_OTP_TRANSPORT: undefined,
    };
    for (const env of [staging, { ...staging, SMS_OTP_TRANSPORT: "at", AT_ENVIRONMENT: "live" }]) {
      const response = await makeHookRequest(
        { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
        {},
        fetchImpl,
        env,
      );
      assertEquals(response.status, 503);
    }
    assertEquals(calls, 0);
  },
);

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
      async () =>
        new Response(atSuccessBody(testCase.code, testCase.status), {
          status: 201,
        }),
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
      new Response(JSON.stringify({ SMSMessageData: { Recipients: [] } }), {
        status: 201,
      }),
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

const wahaTestEnv = {
  ...testEnv,
  SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  SMS_OTP_TRANSPORT: "waha",
  WAHA_OTP_ENABLED: "true",
  WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.vergeo5.com/webhook/convergeo-auth-otp-draft",
  WAHA_OTP_N8N_AUTH_TOKEN: "a".repeat(32),
  WAHA_OTP_N8N_HMAC_SECRET: "b".repeat(32),
};

Deno.test(
  "missing and disabled selectors never send despite usable provider credentials",
  async () => {
    let calls = 0;
    const noFetch: typeof fetch = async () => {
      calls++;
      throw new Error("unexpected provider I/O");
    };
    for (const SUPABASE_URL of [
      undefined,
      wahaTestEnv.SUPABASE_URL,
      "https://other-project.example",
    ]) {
      for (const SMS_OTP_TRANSPORT of [undefined, "", "disabled"]) {
        const response = await makeHookRequest(
          { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
          {},
          noFetch,
          { ...wahaTestEnv, SUPABASE_URL, SMS_OTP_TRANSPORT },
        );
        assertEquals(response.status, 503);
        assertEquals(response.headers.get("content-type"), "application/json");
      }
    }
    assertEquals(calls, 0);
  },
);

Deno.test(
  "WAHA wrong project, missing enablement and invalid selection cannot fall back to AT",
  async () => {
    let calls = 0;
    const noFetch: typeof fetch = async () => {
      calls++;
      throw new Error("unexpected provider I/O");
    };
    const cases = [
      { ...wahaTestEnv, SUPABASE_URL: "https://other-project.example" },
      { ...wahaTestEnv, WAHA_OTP_ENABLED: undefined },
      { ...wahaTestEnv, WAHA_OTP_ENABLED: "false" },
      { ...wahaTestEnv, WAHA_OTP_ENABLED: "TRUE" },
      { ...wahaTestEnv, SMS_OTP_TRANSPORT: "unknown" },
    ];
    for (const env of cases) {
      const response = await makeHookRequest(
        { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
        {},
        noFetch,
        env,
      );
      assertEquals(response.status, env.SMS_OTP_TRANSPORT === "unknown" ? 500 : 503);
    }
    assertEquals(calls, 0);
  },
);

Deno.test(
  "signature verification precedes every transport and produces generic JSON with zero I/O",
  async () => {
    let calls = 0;
    const noFetch: typeof fetch = async () => {
      calls++;
      throw new Error("unexpected provider I/O");
    };
    for (const env of [testEnv, wahaTestEnv, { ...wahaTestEnv, SMS_OTP_TRANSPORT: "disabled" }]) {
      const response = await makeHookRequest(
        { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
        { "webhook-signature": "v1,badsignature" },
        noFetch,
        env,
      );
      assertEquals(response.status, 401);
      assertEquals(JSON.parse(await response.text()), {
        error: { http_code: 401, message: "Invalid hook signature" },
      });
    }
    assertEquals(calls, 0);
  },
);

Deno.test("validly signed but expired handoff cannot reach a provider", async () => {
  const payload = JSON.stringify({ user: { phone: "+260971000099" }, sms: { otp: "654321" } });
  const id = crypto.randomUUID();
  const timestamp = new Date(Date.now() - 10_000);
  const signature = new Webhook(BASE64_SECRET).sign(id, timestamp, payload);
  let calls = 0;
  const response = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", {
      method: "POST",
      body: payload,
      headers: {
        "webhook-id": id,
        "webhook-timestamp": String(Math.floor(timestamp.getTime() / 1000)),
        "webhook-signature": signature,
      },
    }),
    {
      env: wahaTestEnv,
      fetchImpl: async () => {
        calls++;
        throw new Error("unexpected provider I/O");
      },
    },
  );
  assertEquals(response.status, 400);
  assertEquals(calls, 0);
});

Deno.test(
  "WAHA provider errors and PENDING-only receipts return uncertainty without SMS fallback",
  async () => {
    const logs: string[] = [];
    const original = console.log;
    console.log = (...parts) => logs.push(parts.join(" "));
    let calls = 0;
    try {
      const outcomes = [
        () => new Response("fixture sensitive provider error", { status: 503 }),
        () => new Response(JSON.stringify({ status: "PENDING" }), { status: 200 }),
        () => new Response(JSON.stringify({ accepted: true, requestId: "wrong" }), { status: 200 }),
        () => {
          throw new Error("fixture sensitive provider exception");
        },
      ];
      for (const outcome of outcomes) {
        const response = await makeHookRequest(
          { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
          {},
          async (input) => {
            calls++;
            assertEquals(String(input), wahaTestEnv.WAHA_OTP_N8N_WEBHOOK_URL);
            return outcome();
          },
          wahaTestEnv,
        );
        assertEquals(response.status, 503);
        assertEquals(response.headers.get("retry-after"), null);
        assertEquals(JSON.parse(await response.text()), {
          error: { http_code: 503, message: "OTP delivery unavailable" },
        });
      }
      assertEquals(calls, outcomes.length);
      assertEquals(logs.join(" ").includes("fixture sensitive"), false);
      assertEquals(logs.join(" ").includes("654321"), false);
    } finally {
      console.log = original;
    }
  },
);

Deno.test(
  "WAHA lost response aborts exactly one mocked handoff without AT fallback or retry",
  async () => {
    let calls = 0;
    let aborted = false;
    const response = await makeHookRequest(
      { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
      {},
      async (input, init) => {
        calls++;
        assertEquals(String(input), wahaTestEnv.WAHA_OTP_N8N_WEBHOOK_URL);
        return await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => {
              aborted = true;
              reject(new Error("mocked lost response"));
            },
            { once: true },
          );
        });
      },
      wahaTestEnv,
    );
    assertEquals(response.status, 503);
    assertEquals(response.headers.get("retry-after"), null);
    assertEquals(calls, 1);
    assertEquals(aborted, true);
  },
);

Deno.test("explicit sandbox AT remains available on staging and never calls WAHA", async () => {
  let calls = 0;
  const response = await makeHookRequest(
    { user: { phone: "+260971000099" }, sms: { otp: "654321" } },
    {},
    async (input) => {
      calls++;
      assertEquals(String(input), "https://api.sandbox.africastalking.com/version1/messaging");
      return new Response(atSuccessBody(101), { status: 201 });
    },
    { ...testEnv, SUPABASE_URL: wahaTestEnv.SUPABASE_URL },
  );
  assertEquals(response.status, 200);
  assertEquals(calls, 1);
});

Deno.test("non-POST hooks cannot read or send an OTP", async () => {
  let calls = 0;
  const response = await handleSendSmsOtp(
    new Request("http://localhost/send-sms-otp", { method: "GET" }),
    {
      env: wahaTestEnv,
      fetchImpl: async () => {
        calls++;
        throw new Error("unexpected provider I/O");
      },
    },
  );
  assertEquals(response.status, 405);
  assertEquals(calls, 0);
});
