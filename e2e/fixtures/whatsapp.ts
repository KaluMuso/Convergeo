import { expect } from "@playwright/test";

import { whatsapp as waEnv, whatsappMockReady } from "./env";

type MockMessage = {
  to: string;
  template?: string;
  body?: string;
  createdAt?: string;
};

/**
 * Fetch messages delivered through the WhatsApp MOCK adapter's outbox.
 *
 * The app under test must run with its notification adapter in mock mode
 * (`WHATSAPP_MOCK=1` server-side); the mock persists outbound sends to a
 * JSON-readable outbox exposed at `WHATSAPP_MOCK_OUTBOX_URL`. This never hits
 * the real WhatsApp Cloud API and carries only seed-fixture recipients (no real
 * PII).
 */
export async function fetchMockOutbox(to?: string): Promise<MockMessage[]> {
  if (!whatsappMockReady()) return [];
  const url = new URL(waEnv.outboxUrl);
  if (to) url.searchParams.set("to", to);
  const res = await fetch(url, { headers: { accept: "application/json" } });
  if (!res.ok) {
    throw new Error(`WhatsApp mock outbox fetch failed: ${res.status}`);
  }
  const data = (await res.json()) as { messages?: MockMessage[] } | MockMessage[];
  return Array.isArray(data) ? data : (data.messages ?? []);
}

/**
 * Assert a WhatsApp notification matching `template` was queued for `to`.
 * When the mock adapter is not wired (this build env), returns false so the
 * caller can `test.skip()`/annotate rather than fail.
 */
export async function expectWhatsAppMessage(
  to: string,
  template: RegExp | string,
): Promise<boolean> {
  if (!whatsappMockReady()) return false;
  const messages = await fetchMockOutbox(to);
  const matcher =
    typeof template === "string" ? new RegExp(template, "i") : template;
  const hit = messages.some(
    (m) =>
      (m.template && matcher.test(m.template)) ||
      (m.body && matcher.test(m.body)),
  );
  expect(
    hit,
    `expected a WhatsApp mock message for ${to} matching ${matcher}`,
  ).toBeTruthy();
  return true;
}
