// @vitest-environment jsdom
import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";
import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  for (const cookie of document.cookie.split(";")) {
    document.cookie = `${cookie.split("=")[0]?.trim()}=; Max-Age=0; Path=/`;
  }
});

it("exchanges a recovery PKCE code once with the real Auth client and isolated fake transport", async () => {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/auth/v1/recover")) {
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
    }
    if (url.includes("/auth/v1/token")) {
      return new Response(
        JSON.stringify({
          access_token: "fixture-access-token",
          refresh_token: "fixture-refresh-token",
          token_type: "bearer",
          expires_in: 3600,
          user: { id: "recovery-user", app_metadata: {}, user_metadata: {} },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`Unexpected fake Auth request: ${url}`);
  });
  const options = {
    isSingleton: false,
    auth: { detectSessionInUrl: false },
    global: { fetch: fetcher },
  };
  const requestClient = createSupabaseBrowserClient(
    "https://fixture.supabase.test",
    "fixture-publishable-key",
    options,
  );
  const { error: requestError } = await requestClient.auth.resetPasswordForEmail(
    "fixture@example.test",
    { redirectTo: "https://app.example.test/en/reset-password/confirm" },
  );
  expect(requestError).toBeNull();

  window.history.replaceState({}, "", "/en/reset-password/confirm?code=synthetic-code");
  const events: string[] = [];
  const {
    data: { subscription },
  } = requestClient.auth.onAuthStateChange((event) => {
    events.push(event);
  });
  const { data, error } = await requestClient.auth.exchangeCodeForSession("synthetic-code");
  subscription.unsubscribe();

  expect(error).toBeNull();
  expect(data.session?.user.id).toBe("recovery-user");
  expect(events).toContain("PASSWORD_RECOVERY");
  expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/v1/token"))).toHaveLength(
    1,
  );
});
