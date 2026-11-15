import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() =>
  vi.fn((path: string) => {
    throw new Error(`REDIRECT:${path}`);
  }),
);
const notFound = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("NOT_FOUND");
  }),
);
vi.mock("next/navigation", () => ({ redirect, notFound }));

import BrowsePage from "./page";

describe("/[locale]/browse", () => {
  it("redirects to the category index instead of 404ing", async () => {
    await expect(BrowsePage({ params: Promise.resolve({ locale: "en" }) })).rejects.toThrow(
      "REDIRECT:/en/categories",
    );
  });

  it("404s for an unknown locale", async () => {
    await expect(BrowsePage({ params: Promise.resolve({ locale: "xx" }) })).rejects.toThrow(
      "NOT_FOUND",
    );
  });
});
