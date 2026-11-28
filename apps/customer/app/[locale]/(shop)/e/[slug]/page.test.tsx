import { describe, expect, it, vi } from "vitest";

// Calendar links and shared URLs hit /events/{slug}; an unknown slug must 404,
// not 500 when the API cannot resolve postgrest maybe_single().

const { fetchEventDetailMock } = vi.hoisted(() => ({
  fetchEventDetailMock: vi.fn(),
}));

vi.mock("../../_components/detail-fetch/fetch-event", () => ({
  fetchEventDetail: fetchEventDetailMock,
}));

vi.mock("@vergeo/i18n", () => ({
  formatK: (value: number) => `K${value / 100}`,
  loadNamespace: vi.fn().mockResolvedValue({}),
  LOCALES: ["en"],
}));

vi.mock("next-intl", () => ({
  createTranslator: () => (key: string) => key,
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn().mockResolvedValue({ events: {} }),
  setRequestLocale: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({
    get: () => undefined,
  }),
}));

import EventDetailPage from "./page";

const unknownSlug = "calendar-invite-ghost-event";
const pageProps = {
  params: Promise.resolve({ locale: "en", slug: unknownSlug }),
  searchParams: Promise.resolve({}),
};

describe("EventDetailPage unknown slug", () => {
  it("bails out with Next.js 404 for /en/e/<unknown>", async () => {
    fetchEventDetailMock.mockResolvedValue({ kind: "not_found" });

    await expect(EventDetailPage(pageProps)).rejects.toThrow(
      /NEXT_HTTP_ERROR_FALLBACK;404|NEXT_NOT_FOUND/,
    );
    expect(fetchEventDetailMock).toHaveBeenCalledWith(
      unknownSlug,
      expect.objectContaining({ privateGate: false, accessProof: null }),
    );
  });
});
