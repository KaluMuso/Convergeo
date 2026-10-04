import { LOCALES } from "@vergeo/i18n";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResetConfirmForm } from "../../../../../customer/app/[locale]/(auth)/_components/reset-confirm-form";
import { ResetRequestForm } from "../../../../../customer/app/[locale]/(auth)/_components/reset-request-form";
import LoginPage from "../login/page";

import ConfirmPage from "./confirm/page";
import RecoveryLayout from "./layout";
import RecoveryPage from "./page";

vi.mock("next-intl/server", () => ({
  getRequestConfig: (config: unknown) => config,
  setRequestLocale: vi.fn(),
  getMessages: async () => ({}),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

beforeEach(() => {
  // Admin has no JSX Vitest config; Next's JSX pages still need React in this SSR fixture.
  vi.stubGlobal("React", React);
});
afterEach(() => vi.unstubAllGlobals());

describe("admin recovery route wiring in the admin module context", () => {
  it.each(LOCALES)("wires both pages and translated layout for %s", async (locale) => {
    const params = Promise.resolve({ locale });
    const requestPage = await RecoveryPage({ params });
    const confirmPage = await ConfirmPage({ params });
    expect(requestPage?.type).toBe(ResetRequestForm);
    expect(confirmPage?.type).toBe(ResetConfirmForm);
    expect(requestPage?.props.locale).toBe(locale);
    expect(confirmPage?.props.locale).toBe(locale);
    const layout = await RecoveryLayout({ params, children: requestPage });
    expect(layout?.props.locale).toBe(locale);
    expect(layout?.props.messages.auth.reset.requestSubmit).toBeTruthy();
    expect(layout?.props.messages.common.app.name).toBeTruthy();
    const markup = renderToStaticMarkup(layout!);
    expect(markup).toContain("max-w-[360px]");
    expect(markup).toContain('type="email"');
    expect(markup).not.toContain("<nav");
  });

  it("links admin login to the implemented recovery request path", async () => {
    const page = await LoginPage({
      params: Promise.resolve({ locale: "en" }),
      searchParams: Promise.resolve({}),
    });
    const markup = renderToStaticMarkup(page!);
    expect(markup).toContain('href="/en/reset-password"');
    expect(markup).toContain("Forgot password");
  });

  it("rejects unsupported locales in both pages and the layout", async () => {
    const invalid = { params: Promise.resolve({ locale: "xx" }) };
    expect(await RecoveryPage(invalid)).toBeNull();
    expect(await ConfirmPage(invalid)).toBeNull();
    expect(await RecoveryLayout({ ...invalid, children: null })).toBeNull();
  });
});
