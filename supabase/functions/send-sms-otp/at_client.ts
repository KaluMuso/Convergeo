import { type AtEnvironment, resolveAtEnvironment, resolveAtMessagingUrl } from "./at_config.ts";
import { logSmsOtpEvent, maskPhoneTail } from "./logging.ts";

export type AtSendParams = {
  to: string;
  message: string;
  from: string;
  username: string;
  apiKey: string;
  environment: AtEnvironment;
};

export type AtRecipientOutcome = {
  statusCode: number;
  status: string;
  number?: string;
};

export type AtSendResult =
  | { ok: true; status: number; recipient: AtRecipientOutcome }
  | {
      ok: false;
      status: number;
      retryable: boolean;
      message: string;
      recipient?: AtRecipientOutcome;
    };

export type AtFetch = typeof fetch;

const SUCCESS_RECIPIENT_STATUS_CODES = new Set([100, 101, 102]);
const PERMANENT_RECIPIENT_STATUS_CODES = new Set([401, 402, 403, 404, 405, 406, 407, 502]);

type AtResponseBody = {
  SMSMessageData?: {
    Recipients?: Array<Record<string, unknown>>;
  };
};

export function classifyRecipientStatus(statusCode: number): { ok: boolean; retryable: boolean } {
  if (SUCCESS_RECIPIENT_STATUS_CODES.has(statusCode)) {
    return { ok: true, retryable: false };
  }
  if (PERMANENT_RECIPIENT_STATUS_CODES.has(statusCode)) {
    return { ok: false, retryable: false };
  }
  if (statusCode >= 500) {
    return { ok: false, retryable: true };
  }
  return { ok: false, retryable: false };
}

function parseRecipient(raw: unknown): AtRecipientOutcome | undefined {
  if (!raw || typeof raw !== "object") {
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  const statusCode = Number(record.statusCode);
  if (!Number.isFinite(statusCode)) {
    return undefined;
  }
  return {
    statusCode,
    status: String(record.status ?? ""),
    number: typeof record.number === "string" ? record.number : undefined,
  };
}

function parseAtResponseBody(text: string): AtResponseBody | undefined {
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    return parsed as AtResponseBody;
  } catch {
    return undefined;
  }
}

function firstRecipient(body: AtResponseBody | undefined): AtRecipientOutcome | undefined {
  const recipients = body?.SMSMessageData?.Recipients;
  if (!Array.isArray(recipients) || recipients.length === 0) {
    return undefined;
  }
  return parseRecipient(recipients[0]);
}

export function resolveAtClientConfig(env: Record<string, string | undefined>): {
  environment: AtEnvironment;
  messagingUrl: string;
} {
  const environment = resolveAtEnvironment(env.AT_ENVIRONMENT);
  return { environment, messagingUrl: resolveAtMessagingUrl(environment) };
}

export async function sendAtSms(
  params: AtSendParams,
  fetchImpl: AtFetch = fetch,
): Promise<AtSendResult> {
  const messagingUrl = resolveAtMessagingUrl(params.environment);
  const body = new URLSearchParams({
    username: params.username,
    to: params.to,
    message: params.message,
    from: params.from,
  });

  let response: Response;
  try {
    response = await fetchImpl(messagingUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        apiKey: params.apiKey,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logSmsOtpEvent("at_transport_error", {
      at_environment: params.environment,
      retryable: true,
      provider_outcome: "transport_error",
      phone_tail: maskPhoneTail(params.to),
    });
    return { ok: false, status: 502, retryable: true, message };
  }

  const responseText = await response.text();
  const parsed = parseAtResponseBody(responseText);
  const recipient = firstRecipient(parsed);

  if (!response.ok) {
    const retryable = response.status >= 500;
    logSmsOtpEvent("at_http_error", {
      at_environment: params.environment,
      at_http_status: response.status,
      recipient_status_code: recipient?.statusCode ?? null,
      recipient_status: recipient?.status ?? null,
      retryable,
      provider_outcome: "http_error",
      phone_tail: maskPhoneTail(params.to),
    });
    return {
      ok: false,
      status: response.status,
      retryable,
      message: responseText || `Africa's Talking HTTP ${response.status}`,
      recipient,
    };
  }

  if (!recipient) {
    logSmsOtpEvent("at_malformed_response", {
      at_environment: params.environment,
      at_http_status: response.status,
      retryable: false,
      provider_outcome: "missing_recipients",
      phone_tail: maskPhoneTail(params.to),
    });
    return {
      ok: false,
      status: response.status,
      retryable: false,
      message: "Africa's Talking response missing Recipients",
    };
  }

  const classification = classifyRecipientStatus(recipient.statusCode);
  if (!classification.ok) {
    logSmsOtpEvent("at_recipient_rejected", {
      at_environment: params.environment,
      at_http_status: response.status,
      recipient_status_code: recipient.statusCode,
      recipient_status: recipient.status,
      retryable: classification.retryable,
      provider_outcome: "recipient_rejected",
      phone_tail: maskPhoneTail(params.to),
    });
    return {
      ok: false,
      status: response.status,
      retryable: classification.retryable,
      message: `Africa's Talking recipient status ${recipient.statusCode} (${recipient.status})`,
      recipient,
    };
  }

  logSmsOtpEvent("at_recipient_accepted", {
    at_environment: params.environment,
    at_http_status: response.status,
    recipient_status_code: recipient.statusCode,
    recipient_status: recipient.status,
    retryable: false,
    provider_outcome: "accepted",
    phone_tail: maskPhoneTail(params.to),
  });

  return { ok: true, status: response.status, recipient };
}
