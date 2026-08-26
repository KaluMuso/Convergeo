// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import authMessages from "../../../../../../packages/i18n/messages/en/auth.json";
import commonMessages from "../../../../../../packages/i18n/messages/en/common.json";

// No component-rendering test infrastructure (@testing-library/react,
// jest-dom) exists in apps/admin (see ../../not-found.test.tsx) — this
// renders to a static HTML string with react-dom/server instead of adding
// that dependency for this one page. AuthLoginShell's useEffect never runs
// under renderToStaticMarkup (no hydration), so unlike the RTL-based vendor
// equivalent this needs no @vergeo/auth/browser-client-lazy mock either.
vi.mock("@vergeo/i18n", () => ({
  loadNamespace: vi.fn(async (_locale: string, namespace: string) =>
    namespace === "auth" ? authMessages : namespace === "common" ? commonMessages : {},
  ),
  LOCALES: ["en", "bem", "nya", "fr", "zh"],
}));

function lookup(messages: Record<string, unknown>, namespace: string, key: string): string {
  const ns = messages[namespace] as Record<string, unknown> | undefined;
  const value = key.split(".").reduce<unknown>((acc, part) => {
    return acc && typeof acc === "object" ? (acc as Record<string, unknown>)[part] : undefined;
  }, ns);
  return typeof value === "string" ? value : key;
}

vi.mock("next-intl", () => ({
  createTranslator: ({
    messages,
    namespace,
  }: {
    messages: Record<string, unknown>;
    namespace: string;
  }) => {
    const t = (key: string) => lookup(messages, namespace, key);
    t.raw = t;
    return t;
  },
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({}),
  setRequestLocale: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

import AdminLoginPage from "./page";

/**
 * PR-D (VENDOR_PHONE_OTP=ENABLED) only turns phone login on for Vendor.
 * ADMIN_PHONE_OTP stays disabled — Admin must keep going through email/password
 * only, with no phone/email toggle. Renders the REAL page (real auth.json
 * content) so a future accidental `phoneEnabled` flip on Admin (e.g. a
 * careless copy-paste from the Vendor page) fails this test.
 */
describe("admin login page", () => {
  it("keeps phone authentication disabled — email/password only, no toggle", async () => {
    const html = renderToStaticMarkup(
      await AdminLoginPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(html).toContain(authMessages.email.emailLabel);
    expect(html).toContain(authMessages.email.passwordLabel);
    expect(html).not.toContain('type="tel"');
    expect(html).not.toContain(authMessages.login.phoneLabel);
    expect(html).not.toContain(authMessages.login.emailToggle);
    expect(html).not.toContain(authMessages.login.phoneToggle);
  });
});
