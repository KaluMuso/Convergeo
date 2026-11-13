import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  sendWahaOtp,
  selectOtpTransport,
} from "../../supabase/functions/send-sms-otp/waha_transport.ts";
import {
  workflow,
  validateCode,
  verifyCode,
  reservationCode,
  receiptCode,
} from "./build-waha-otp-handoff.mjs";

const originalFetch = globalThis.fetch;
let unexpectedNetworkCalls = 0;
before(() => {
  globalThis.fetch = () => {
    unexpectedNetworkCalls += 1;
    throw new Error("unexpected network call in inactive-template test");
  };
});
after(() => {
  globalThis.fetch = originalFetch;
  assert.equal(unexpectedNetworkCalls, 0);
});

const now = 1_800_000_000_000;
const body = {
  version: 1,
  requestId: "request_12345678",
  timestamp: now / 1000,
  deadline: now + 3500,
  phone: "+260971000099",
  otp: "654321",
};
const signature = createHmac("sha256", "b".repeat(32))
  .update(["v1", body.timestamp, body.requestId, body.deadline, body.phone, body.otp].join("\n"))
  .digest("hex");
const run = (
  code,
  value,
  lookup = () => {
    throw Error("unexpected lookup");
  },
  at = now,
) =>
  new Function("$input", "$", "Date", code)({ first: () => ({ json: value }) }, lookup, {
    now: () => at,
  });

test("generated source and JSON match and remain inert with completed-execution saving off", () => {
  const saved = JSON.parse(
    readFileSync(fileURLToPath(new URL("./waha-otp-handoff.json", import.meta.url)), "utf8"),
  );
  assert.deepEqual(saved, workflow);
  assert.equal(saved.active, false);
  assert.equal(saved.nodes.find((n) => n.id === "send-waha").disabled, true);
  const hmac = saved.nodes.find((n) => n.id === "compute-hmac");
  assert.equal(hmac.typeVersion, 1);
  assert.equal(hmac.disabled, true);
  assert.equal(hmac.parameters.secret, "");
  assert.equal(hmac.credentials, undefined);
  assert.deepEqual(saved.pinData, {});
  assert.equal(saved.settings.saveDataSuccessExecution, "none");
  assert.equal(saved.settings.saveDataErrorExecution, "none");
  assert.equal(saved.settings.saveManualExecutions, false);
  assert.equal(saved.settings.saveExecutionProgress, false);
  assert.equal(saved.settings.errorWorkflow, undefined);
  assert.equal(
    saved.nodes.some((n) => /schedule|wait|queue|errorTrigger/i.test(n.type)),
    false,
  );
  assert.equal(saved.nodes.find((n) => n.id === "send-waha").retryOnFail, false);
  assert.deepEqual(saved.nodes.find((n) => n.id === "send-waha").parameters.options, {
    timeout: 1500,
    redirect: { redirect: { followRedirects: false } },
    sendCredentialsOnCrossOriginRedirect: false,
  });
  assert.equal(
    saved.nodes.find((n) => n.id === "otp-webhook").parameters.authentication,
    "headerAuth",
  );
  assert.equal(
    saved.nodes.find((n) => n.id === "otp-webhook").parameters.responseMode,
    "responseNode",
  );
  assert.equal(
    saved.nodes
      .find((n) => n.id === "reserve-request")
      .parameters.query.includes("ON CONFLICT DO NOTHING RETURNING"),
    true,
  );
  assert.equal(saved.nodes.find((n) => n.id === "reserve-request").typeVersion, 2.5);
  assert.equal(
    saved.nodes.find((n) => n.id === "reserve-request").parameters.options.queryReplacement,
    "={{ [$json.requestId, $json.deadline] }}",
  );
  assert.equal(saved.nodes.find((n) => n.id === "reserve-request").alwaysOutputData, false);
  assert.equal(
    /phone|message|\$3/i.test(saved.nodes.find((n) => n.id === "reserve-request").parameters.query),
    false,
  );
  assert.equal(
    saved.nodes
      .flatMap((n) => Object.values(n.credentials ?? {}))
      .every((credential) => credential.id.startsWith("REPLACE_WITH_")),
    true,
  );
  assert.equal(JSON.stringify(saved).includes("654321"), false);
  assert.equal(
    saved.nodes.some((n) =>
      ["console.", "log(", "fetch("].some((needle) => (n.parameters.jsCode ?? "").includes(needle)),
    ),
    false,
  );
});

test("the unbound HMAC and disabled send paths cannot manufacture an acceptance", () => {
  const validated = run(validateCode, {
    body,
    headers: { "x-convergeo-otp-signature": signature },
  })[0].json;
  // A disabled Crypto node forwards validated input, which has no calculated HMAC.
  assert.equal(validated.calculated, undefined);
  assert.throws(() => run(verifyCode, validated), /invalid otp signature/);
  // Even if a future owner binds HMAC, bypassing the disabled send node produces no provider ID.
  assert.throws(
    () => run(receiptCode, body, () => ({ first: () => ({ json: body }) })),
    /otp provider not confirmed/,
  );
});

test("receiver graph orders authentication, reservation, single send and small JSON response", () => {
  const names = workflow.nodes.map((node) => node.name);
  assert.equal(names.length, 9);
  for (let i = 0; i < names.length - 1; i++) {
    assert.deepEqual(workflow.connections[names[i]], {
      main: [[{ node: names[i + 1], type: "main", index: 0 }]],
    });
  }
  const response = workflow.nodes.find((node) => node.id === "respond");
  assert.deepEqual(response.parameters, {
    respondWith: "firstIncomingItem",
    options: { responseCode: 200 },
  });
  assert.equal(workflow.nodes.filter((node) => node.type.endsWith("httpRequest")).length, 1);
  assert.equal(
    workflow.nodes.some((node) => node.continueOnFail || node.onError),
    false,
  );
});

test("deadline is rechecked after mocked HMAC computation and reservation", () => {
  const validated = run(validateCode, {
    body,
    headers: { "x-convergeo-otp-signature": signature },
  })[0].json;
  assert.throws(
    () => run(verifyCode, { ...validated, calculated: signature }, undefined, body.deadline),
    /invalid otp signature/,
  );
  const lookup = () => ({ first: () => ({ json: body }) });
  assert.throws(
    () => run(reservationCode, { requestId: body.requestId }, lookup, body.deadline),
    /otp replay or deadline/,
  );
});

const mockEnv = {
  SUPABASE_URL: "https://iyasmrmbcrvlfxpzescb.supabase.co",
  SMS_OTP_TRANSPORT: "waha",
  WAHA_OTP_ENABLED: "true",
  WAHA_OTP_N8N_WEBHOOK_URL: "https://n8n.vergeo5.com/webhook/convergeo-auth-otp-draft",
  WAHA_OTP_N8N_AUTH_TOKEN: "a".repeat(32),
  WAHA_OTP_N8N_HMAC_SECRET: "b".repeat(32),
};
const mockPayload = { user: { phone: body.phone }, sms: { otp: body.otp } };
const mockHeaders = () =>
  new Headers({
    "webhook-id": body.requestId,
    "webhook-timestamp": String(body.timestamp),
  });

// Protocol simulation only: HMAC computation and provider acceptance are supplied by mocks.
// This does not execute n8n, enable either disabled node, or use a real replay database/provider.
function mockReceiver({
  providerResponse = { id: "synthetic-message-id" },
  databaseOutage = false,
  invalidHmac = false,
  loseReceipt = false,
} = {}) {
  const requestIds = new Set();
  const providerCalls = [];
  let handoffs = 0;
  const fetchImpl = async (url, init) => {
    handoffs += 1;
    assert.equal(url, mockEnv.WAHA_OTP_N8N_WEBHOOK_URL);
    assert.equal(init.redirect, "error");
    assert.equal(init.headers["X-Convergeo-OTP-Auth"], mockEnv.WAHA_OTP_N8N_AUTH_TOKEN);
    const verifiedEnvelope = run(validateCode, {
      body: JSON.parse(init.body),
      headers: { "x-convergeo-otp-signature": init.headers["X-Convergeo-OTP-Signature"] },
    })[0].json;
    const calculated = createHmac("sha256", mockEnv.WAHA_OTP_N8N_HMAC_SECRET)
      .update(verifiedEnvelope.signingInput)
      .digest("hex");
    let verified;
    try {
      verified = run(verifyCode, {
        ...verifiedEnvelope,
        calculated: invalidHmac ? "0".repeat(64) : calculated,
      })[0].json;
    } catch {
      return new Response("{}", { status: 401 });
    }
    if (databaseOutage || requestIds.has(verified.requestId)) {
      return new Response("{}", { status: 503 });
    }
    requestIds.add(verified.requestId);
    const lookup = () => ({ first: () => ({ json: verified }) });
    run(reservationCode, { requestId: verified.requestId }, lookup);
    providerCalls.push({ requestId: verified.requestId, phone: verified.phone });
    let receipt;
    try {
      receipt = run(receiptCode, providerResponse, lookup)[0].json;
    } catch {
      return new Response("{}", { status: 503 });
    }
    if (loseReceipt) throw new Error("synthetic lost receipt after mock provider acceptance");
    assert.deepEqual(Object.keys(receipt).sort(), ["accepted", "requestId"]);
    return new Response(JSON.stringify(receipt), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { fetchImpl, requestIds, providerCalls, handoffs: () => handoffs };
}

test("actual Edge handoff envelope and HMAC match mocked receiver acceptance", async () => {
  assert.equal(selectOtpTransport({}), "disabled");
  assert.equal(selectOtpTransport(mockEnv), "waha");
  for (const providerResponse of [
    { id: "synthetic-message-id" },
    {
      key: { id: "synthetic-nested-id", fromMe: true, remoteJid: "260971000099@s.whatsapp.net" },
      status: "PENDING",
    },
  ]) {
    const receiver = mockReceiver({ providerResponse });
    assert.deepEqual(
      await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
      { ok: true },
    );
    assert.equal(receiver.handoffs(), 1);
    assert.equal(receiver.providerCalls.length, 1);
    assert.equal(receiver.requestIds.size, 1);
  }
});

test("mocked receiver reservation permits only one provider call for repeated Edge identity", async () => {
  const receiver = mockReceiver();
  assert.deepEqual(
    await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
    { ok: true },
  );
  assert.deepEqual(
    await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
    { ok: false, status: 503 },
  );
  assert.equal(receiver.handoffs(), 2);
  assert.equal(receiver.providerCalls.length, 1);
  assert.equal(receiver.requestIds.size, 1);
});

test("mocked signature or reservation failure stops before provider work", async () => {
  for (const options of [{ invalidHmac: true }, { databaseOutage: true }]) {
    const receiver = mockReceiver(options);
    assert.deepEqual(
      await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
      { ok: false, status: 503 },
    );
    assert.equal(receiver.handoffs(), 1);
    assert.equal(receiver.providerCalls.length, 0);
    assert.equal(receiver.requestIds.size, 0);
  }
});

test("PENDING-only and mismatched provider receipts remain uncertain without another send", async () => {
  for (const providerResponse of [
    { status: "PENDING" },
    {
      key: { id: "synthetic-nested-id", fromMe: true, remoteJid: "260971000098@c.us" },
      status: "PENDING",
    },
  ]) {
    const receiver = mockReceiver({ providerResponse });
    for (let attempt = 0; attempt < 2; attempt++) {
      assert.deepEqual(
        await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
        { ok: false, status: 503 },
      );
    }
    assert.equal(receiver.handoffs(), 2);
    assert.equal(receiver.providerCalls.length, 1);
  }
});

test("lost mock acceptance receipt is uncertain and a caller retry does not resend", async () => {
  const receiver = mockReceiver({ loseReceipt: true });
  for (let attempt = 0; attempt < 2; attempt++) {
    assert.deepEqual(
      await sendWahaOtp(mockPayload, mockHeaders(), mockEnv, receiver.fetchImpl, now),
      { ok: false, status: 503 },
    );
  }
  assert.equal(receiver.handoffs(), 2);
  assert.equal(receiver.providerCalls.length, 1);
});

test("receiver validates the exact envelope and HMAC before reservation", () => {
  const validated = run(validateCode, {
    body,
    headers: { "x-convergeo-otp-signature": signature },
  })[0].json;
  assert.equal(
    validated.signingInput,
    ["v1", body.timestamp, body.requestId, body.deadline, body.phone, body.otp].join("\n"),
  );
  const calculated = createHmac("sha256", "b".repeat(32))
    .update(validated.signingInput)
    .digest("hex");
  assert.deepEqual(run(verifyCode, { ...validated, calculated })[0].json, {
    requestId: body.requestId,
    deadline: body.deadline,
    phone: body.phone,
    otp: body.otp,
  });
  assert.throws(
    () => run(verifyCode, { ...validated, calculated: "0".repeat(64) }),
    /invalid otp signature/,
  );
});

test("receiver rejects missing signature, stale envelope and wrong recipient shape", () => {
  assert.throws(() => run(validateCode, { body, headers: {} }), /invalid otp handoff/);
  assert.throws(
    () =>
      run(validateCode, {
        body: { ...body, timestamp: body.timestamp - 31 },
        headers: { "x-convergeo-otp-signature": signature },
      }),
    /invalid otp handoff/,
  );
  assert.throws(
    () =>
      run(validateCode, {
        body: { ...body, phone: "260971000099@g.us" },
        headers: { "x-convergeo-otp-signature": signature },
      }),
    /invalid otp handoff/,
  );
  assert.throws(
    () =>
      run(validateCode, {
        body: { ...body, extra: true },
        headers: { "x-convergeo-otp-signature": signature },
      }),
    /invalid otp handoff/,
  );
});

test("reservation contract blocks a repeated request ID and checks deadline again", () => {
  const validated = {
    requestId: body.requestId,
    deadline: body.deadline,
    phone: body.phone,
    otp: body.otp,
  };
  const lookup = () => ({ first: () => ({ json: validated }) });
  const databasePrimaryKeys = new Set();
  function reserve(id) {
    if (databasePrimaryKeys.has(id)) return [];
    databasePrimaryKeys.add(id);
    return [{ requestId: id }];
  }
  assert.deepEqual(run(reservationCode, reserve(body.requestId)[0], lookup)[0].json, validated);
  assert.deepEqual(reserve(body.requestId), []);
  assert.throws(() => run(reservationCode, { requestId: "different" }, lookup), /otp replay/);
});

test("only a provider acceptance with an ID can produce the small receipt", () => {
  const lookup = () => ({ first: () => ({ json: body }) });
  const nestedAcceptance = {
    key: {
      remoteJid: "260971000099@c.us",
      fromMe: true,
      id: "nested-message-id-123",
    },
    message: { extendedTextMessage: { text: "synthetic message" } },
    messageTimestamp: "1800000000",
    status: "PENDING",
  };
  const observedAcceptance = {
    ...nestedAcceptance,
    key: {
      ...nestedAcceptance.key,
      remoteJid: "260971000099@s.whatsapp.net",
    },
  };
  assert.deepEqual(run(receiptCode, { id: "message-id-123" }, lookup), [
    { json: { accepted: true, requestId: body.requestId } },
  ]);
  assert.deepEqual(run(receiptCode, nestedAcceptance, lookup), [
    { json: { accepted: true, requestId: body.requestId } },
  ]);
  assert.deepEqual(run(receiptCode, observedAcceptance, lookup), [
    { json: { accepted: true, requestId: body.requestId } },
  ]);
  assert.throws(
    () => run(receiptCode, { id: "message-id-123" }, lookup, body.deadline),
    /otp provider not confirmed/,
  );
  assert.throws(
    () => run(receiptCode, nestedAcceptance, lookup, body.deadline),
    /otp provider not confirmed/,
  );
  for (const result of [{}, { id: "" }, { error: "offline" }, { id: 1 }]) {
    assert.throws(() => run(receiptCode, result, lookup), /otp provider not confirmed/);
  }
  for (const result of [
    { status: "PENDING" },
    { ...nestedAcceptance, key: { ...nestedAcceptance.key, id: "" } },
    { ...nestedAcceptance, key: { ...nestedAcceptance.key, id: "short" } },
    {
      ...nestedAcceptance,
      key: { ...nestedAcceptance.key, id: "x".repeat(257) },
    },
    { ...nestedAcceptance, key: { ...nestedAcceptance.key, fromMe: false } },
    {
      ...nestedAcceptance,
      key: { ...nestedAcceptance.key, remoteJid: "260971000098@c.us" },
    },
    {
      ...observedAcceptance,
      key: { ...observedAcceptance.key, remoteJid: "260971000098@s.whatsapp.net" },
    },
    {
      ...observedAcceptance,
      key: { ...observedAcceptance.key, remoteJid: "260971000099@g.us" },
    },
    {
      ...observedAcceptance,
      key: { ...observedAcceptance.key, remoteJid: "260971000099@broadcast" },
    },
    {
      ...observedAcceptance,
      key: { ...observedAcceptance.key, remoteJid: "260971000099@other.example" },
    },
    { ...nestedAcceptance, status: "FAILED" },
    { ...nestedAcceptance, id: "different-message-id" },
  ]) {
    assert.throws(() => run(receiptCode, result, lookup), /otp provider not confirmed/);
  }
  for (const statusCode of [307, 308]) {
    assert.throws(
      () =>
        run(
          receiptCode,
          {
            statusCode,
            headers: { location: "https://other.example/api/sendText" },
          },
          lookup,
        ),
      /otp provider not confirmed/,
    );
  }
});
