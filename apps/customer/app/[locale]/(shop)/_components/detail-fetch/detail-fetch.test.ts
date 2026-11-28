import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (p: string) => `https://api.example.test${p}`,
  getApiBaseUrl: () => "https://api.example.test",
}));
import { fetchEventDetail } from "./fetch-event";
import { fetchServiceDetail } from "./fetch-service";
const originalFetch = globalThis.fetch;
afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
});
describe("detail fetch", () => {
  it("service 404", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 404 })) as typeof fetch;
    await expect(fetchServiceDetail("x")).resolves.toEqual({ kind: "not_found" });
  });
  it("event private gate", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 404 })) as typeof fetch;
    await expect(fetchEventDetail("x", { privateGate: true })).resolves.toEqual({
      kind: "private_access",
    });
  });
  it("event 404 without private gate", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 404 })) as typeof fetch;
    await expect(fetchEventDetail("no-such-event")).resolves.toEqual({ kind: "not_found" });
  });
});
