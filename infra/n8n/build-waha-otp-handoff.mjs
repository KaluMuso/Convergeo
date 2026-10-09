import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Source-only draft. Running this file writes an inactive workflow JSON beside it.
export const validateCode = `
const input = $input.first().json;
const body = input?.body;
const signature = input?.headers?.['x-convergeo-otp-signature'];
const fail = () => { throw new Error('invalid otp handoff'); };
if (!body || typeof body !== 'object' || Array.isArray(body)) fail();
if (Object.keys(body).sort().join(',') !== 'deadline,otp,phone,requestId,timestamp,version') fail();
const { version, requestId, timestamp, deadline, phone, otp } = body;
const now = Date.now();
if (version !== 1 || typeof requestId !== 'string' || !/^[A-Za-z0-9_-]{8,64}$/.test(requestId)) fail();
if (!Number.isInteger(timestamp) || timestamp * 1000 < now - 30000 || timestamp * 1000 > now + 5000) fail();
if (!Number.isInteger(deadline) || deadline <= now || deadline > timestamp * 1000 + 5000 || deadline > now + 5000) fail();
if (typeof phone !== 'string' || !/^\\+[1-9][0-9]{7,14}$/.test(phone)) fail();
if (typeof otp !== 'string' || !/^[0-9]{4,8}$/.test(otp)) fail();
if (typeof signature !== 'string' || !/^[a-f0-9]{64}$/.test(signature)) fail();
const signingInput = ['v1', timestamp, requestId, deadline, phone, otp].join('\\n');
return [{ json: { requestId, timestamp, deadline, phone, otp, signature, signingInput } }];
`.trim();

export const verifyCode = `
const item = $input.first().json;
const expected = item?.calculated;
const provided = item?.signature;
if (typeof expected !== 'string' || typeof provided !== 'string' || expected.length !== 64 || provided.length !== 64) throw new Error('invalid otp signature');
let difference = 0;
for (let i = 0; i < 64; i++) difference |= expected.charCodeAt(i) ^ provided.charCodeAt(i);
if (difference !== 0 || item.deadline <= Date.now()) throw new Error('invalid otp signature');
return [{ json: { requestId: item.requestId, deadline: item.deadline, phone: item.phone, otp: item.otp } }];
`.trim();

export const reservationCode = `
const item = $input.first().json;
const verified = $('Verify Signature').first().json;
if (item?.requestId !== verified.requestId || verified.deadline <= Date.now()) throw new Error('otp replay or deadline');
return [{ json: verified }];
`.trim();

export const receiptCode = `
const response = $input.first().json;
const verified = $('Verify Signature').first().json;
if (verified.deadline <= Date.now() || !response || typeof response.id !== 'string' || response.id.length < 8 || response.id.length > 256) throw new Error('otp provider not confirmed');
return [{ json: { accepted: true, requestId: verified.requestId } }];
`.trim();

const node = (id, name, type, typeVersion, parameters, position, extra = {}) => ({
  id,
  name,
  type: `n8n-nodes-base.${type}`,
  typeVersion,
  parameters,
  position,
  ...extra,
});
const link = (to) => ({ main: [[{ node: to, type: "main", index: 0 }]] });

export const workflow = {
  name: "DRAFT INACTIVE - Supabase OTP to WAHA",
  active: false,
  nodes: [
    node(
      "otp-webhook",
      "Dedicated OTP Webhook",
      "webhook",
      2.1,
      {
        httpMethod: "POST",
        path: "convergeo-auth-otp-draft",
        authentication: "headerAuth",
        responseMode: "responseNode",
        options: {},
      },
      [200, 300],
      {
        credentials: {
          httpHeaderAuth: {
            id: "REPLACE_WITH_DEDICATED_OTP_HEADER_AUTH_ID",
            name: "Dedicated OTP webhook auth",
          },
        },
      },
    ),
    node(
      "validate-envelope",
      "Validate Envelope",
      "code",
      2,
      { mode: "runOnceForAllItems", jsCode: validateCode },
      [430, 300],
    ),
    node(
      "compute-hmac",
      "Compute HMAC",
      "crypto",
      2,
      {
        action: "hmac",
        binaryData: false,
        type: "SHA256",
        value: "={{ $json.signingInput }}",
        dataPropertyName: "calculated",
        encoding: "hex",
      },
      [660, 300],
      {
        credentials: {
          crypto: {
            id: "REPLACE_WITH_DEDICATED_OTP_HMAC_ID",
            name: "Dedicated OTP HMAC",
          },
        },
      },
    ),
    node(
      "verify-signature",
      "Verify Signature",
      "code",
      2,
      { mode: "runOnceForAllItems", jsCode: verifyCode },
      [890, 300],
    ),
    node(
      "reserve-request",
      "Reserve Request ID",
      "postgres",
      2.5,
      {
        operation: "executeQuery",
        query:
          "INSERT INTO otp_delivery_replay (request_id, expires_at) VALUES ($1, to_timestamp($2::double precision / 1000) + interval '1 day') ON CONFLICT DO NOTHING RETURNING request_id AS \"requestId\"",
        options: {
          queryReplacement: "={{ [$json.requestId, $json.deadline] }}",
        },
      },
      [1120, 300],
      {
        alwaysOutputData: false,
        credentials: {
          postgres: {
            id: "REPLACE_WITH_DEDICATED_REPLAY_DB_ID",
            name: "OTP replay reservation only",
          },
        },
      },
    ),
    node(
      "require-reservation",
      "Require Reservation",
      "code",
      2,
      { mode: "runOnceForAllItems", jsCode: reservationCode },
      [1350, 300],
    ),
    node(
      "send-waha",
      "Send One WAHA Text - DISABLED",
      "httpRequest",
      4.2,
      {
        method: "POST",
        url: "http://waha-otp:3000/api/sendText",
        authentication: "genericCredentialType",
        genericAuthType: "httpHeaderAuth",
        sendBody: true,
        specifyBody: "json",
        jsonBody:
          '={{ JSON.stringify({ session: "default", chatId: $json.phone.slice(1) + "@c.us", text: "Your Vergeo5 code is " + $json.otp }) }}',
        options: {
          timeout: 1500,
          redirect: { redirect: { followRedirects: false } },
          sendCredentialsOnCrossOriginRedirect: false,
        },
      },
      [1580, 300],
      {
        disabled: true,
        retryOnFail: false,
        credentials: {
          httpHeaderAuth: {
            id: "REPLACE_WITH_OWNER_SEND_ONLY_WAHA_CREDENTIAL_ID",
            name: "Owner WAHA send-only",
          },
        },
      },
    ),
    node(
      "check-receipt",
      "Check WAHA Acceptance",
      "code",
      2,
      { mode: "runOnceForAllItems", jsCode: receiptCode },
      [1810, 300],
    ),
    node(
      "respond",
      "Respond After Acceptance",
      "respondToWebhook",
      1.1,
      { respondWith: "firstIncomingItem", options: { responseCode: 200 } },
      [2040, 300],
    ),
  ],
  connections: {
    "Dedicated OTP Webhook": link("Validate Envelope"),
    "Validate Envelope": link("Compute HMAC"),
    "Compute HMAC": link("Verify Signature"),
    "Verify Signature": link("Reserve Request ID"),
    "Reserve Request ID": link("Require Reservation"),
    "Require Reservation": link("Send One WAHA Text - DISABLED"),
    "Send One WAHA Text - DISABLED": link("Check WAHA Acceptance"),
    "Check WAHA Acceptance": link("Respond After Acceptance"),
  },
  settings: {
    executionOrder: "v1",
    saveDataSuccessExecution: "none",
    saveDataErrorExecution: "none",
    saveManualExecutions: false,
    saveExecutionProgress: false,
  },
  pinData: {},
};

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  writeFileSync(
    fileURLToPath(new URL("./waha-otp-handoff.json", import.meta.url)),
    JSON.stringify(workflow, null, 2) + "\n",
  );
}
