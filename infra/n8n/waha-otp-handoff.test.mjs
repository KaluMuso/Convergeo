import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  workflow,
  validateCode,
  verifyCode,
  reservationCode,
  receiptCode,
} from "./build-waha-otp-handoff.mjs";

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
  assert.deepEqual(run(receiptCode, { id: "message-id-123" }, lookup), [
    { json: { accepted: true, requestId: body.requestId } },
  ]);
  assert.throws(
    () => run(receiptCode, { id: "message-id-123" }, lookup, body.deadline),
    /otp provider not confirmed/,
  );
  for (const result of [{}, { id: "" }, { error: "offline" }, { id: 1 }]) {
    assert.throws(() => run(receiptCode, result, lookup), /otp provider not confirmed/);
  }
  for (const statusCode of [307, 308]) {
    assert.throws(
      () =>
        run(
          receiptCode,
          { statusCode, headers: { location: "https://other.example/api/sendText" } },
          lookup,
        ),
      /otp provider not confirmed/,
    );
  }
});
