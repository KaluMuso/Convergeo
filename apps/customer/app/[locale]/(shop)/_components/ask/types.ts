import { ApiError } from "@vergeo/config";

/** Mirror of the API `CitationRef` (services/api/app/services/ask/citations.py). */
export type AskCitation = {
  entity_kind: string;
  entity_id: string;
  title: string;
  price_display: string | null;
};

/** Mirror of the API `AskResponse` (services/api/app/routers/ask.py) — NON-STREAMING. */
export type AskResponse = {
  query: string;
  answer: string;
  citations: AskCitation[];
  cached: boolean;
  refused: boolean;
  message_key: string | null;
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
