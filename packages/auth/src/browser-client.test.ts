import { describe, expect, it } from "vitest";

import { createBrowserClient, resetBrowserClientForTests } from "./browser-client";

describe("createBrowserClient", () => {
  it("constructs a singleton browser client with public env vars", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
    resetBrowserClientForTests();

    const client = createBrowserClient();
    expect(client).toBeDefined();
    expect(client.auth).toBeDefined();
    expect(createBrowserClient()).toBe(client);
  });

  it("throws when public env vars are missing", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    resetBrowserClientForTests();

    expect(() => createBrowserClient()).toThrow(/NEXT_PUBLIC_SUPABASE_URL/);
  });
});
