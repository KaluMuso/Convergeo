import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createBrowserClient, resetBrowserClientForTests } from "./browser-client";

const createSupabaseBrowserClient = vi.fn();

vi.mock("@supabase/ssr", () => ({
  createBrowserClient: (...args: unknown[]) => createSupabaseBrowserClient(...args),
}));

describe("createBrowserClient", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
    resetBrowserClientForTests();
    createSupabaseBrowserClient.mockReturnValue({ auth: {} });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("constructs a singleton browser client with public env vars", () => {
    const client = createBrowserClient();

    expect(client).toBeDefined();
    expect(client.auth).toBeDefined();
    expect(createBrowserClient()).toBe(client);
    expect(createSupabaseBrowserClient).toHaveBeenCalledWith(
      "https://example.supabase.co",
      "anon-key",
    );
    expect(createSupabaseBrowserClient).toHaveBeenCalledOnce();
  });

  it("throws when public env vars are missing", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    resetBrowserClientForTests();

    expect(() => createBrowserClient()).toThrow(/NEXT_PUBLIC_SUPABASE_URL/);
  });
});
