import { ApiError } from "@vergeo/config";

/** Mirror of the API `CitationRef` (services/api/app/services/ask/citations.py). */
export type AskCitation = {
  entity_kind: string;
  entity_id: string;
  title: string;
  price_display: string | null;
  /** Public route slug resolved server-side; the card builds the href from it. */
  slug?: string | null;
  in_stock?: boolean | null;
  distance_km?: number | null;
};

/** Mirror of `FaqRef` (services/api/app/services/ask/faq.py) — i18n keys only. */
export type AskFaq = {
  id: string;
  question_key: string;
  answer_key: string;
};

/** Mirror of `OrderRef` (services/api/app/services/ask/intents.py). */
export type AskOrder = {
  id: string;
  ref: string;
  status: string;
  status_key: string;
  fulfilment?: string | null;
  created_at?: string | null;
};

/** Mirror of `AskQuota` — remaining AI questions today for this caller. */
export type AskQuota = {
  tier: "guest" | "free" | "premium" | string;
  daily_limit: number;
  used: number;
  remaining: number;
};

export type AskSource = "ai" | "workflow" | "fallback";

/** Mirror of the API `AskResponse` (services/api/app/routers/ask.py) — NON-STREAMING. */
export type AskResponse = {
  query: string;
  answer: string;
  citations: AskCitation[];
  cached: boolean;
  refused: boolean;
  message_key: string | null;
  // --- Ask Vergeo upgrade (optional so older payloads still parse) ---
  source?: AskSource;
  intent?: string | null;
  answer_key?: string | null;
  answer_params?: Record<string, string | number>;
  notice_key?: string | null;
  signup_prompt_key?: string | null;
  faq?: AskFaq[];
  orders?: AskOrder[];
  needs_location?: boolean;
  sign_in_required?: boolean;
  quota?: AskQuota | null;
};

export type AskErrorState = {
  /** Fully-qualified i18n key (e.g. `ai.quota.guestExceeded`). */
  messageKey: string;
  /** Present only for the guest-exceeded case (e.g. `ai.quota.signupPrompt`). */
  signupPromptKey: string | null;
};

const AI_PREFIX = "ai.";

/** Strip the `ai.` namespace prefix so the key is usable under `useTranslations("ai")`. */
export function relativeAiKey(fullKey: string): string {
  return fullKey.startsWith(AI_PREFIX) ? fullKey.slice(AI_PREFIX.length) : fullKey;
}

function stringField(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Resolve the banner message key from an API error envelope.
 * Quota errors carry `details.i18n_key`; rate-limit errors carry `details.message_key`;
 * network failures surface as `code === "network_error"`.
 */
export function extractErrorState(error: unknown): AskErrorState {
  if (error instanceof ApiError) {
    if (error.code === "network_error") {
      return { messageKey: "ai.ask.networkError", signupPromptKey: null };
    }
    const details = error.details ?? {};
    const messageKey =
      stringField(details, "message_key") ??
      stringField(details, "i18n_key") ??
      (error.message.startsWith(AI_PREFIX) ? error.message : "ai.answer.unavailable");
    return {
      messageKey,
      signupPromptKey: stringField(details, "signup_prompt_key"),
    };
  }
  return { messageKey: "ai.ask.networkError", signupPromptKey: null };
}

/** Only accept a well-formed quota object from the wire. */
export function parseQuota(value: unknown): AskQuota | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const { tier, daily_limit: dailyLimit, used, remaining } = record;
  if (
    typeof tier !== "string" ||
    typeof dailyLimit !== "number" ||
    typeof used !== "number" ||
    typeof remaining !== "number"
  ) {
    return null;
  }
  return { tier, daily_limit: dailyLimit, used, remaining: Math.max(0, remaining) };
}
