// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomerSession } from "./auth-transition";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  unsubscribe: vi.fn(),
  mergeGuestCartIntoAccount: vi.fn(),
}));

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: mocks.onAuthStateChange,
    },
  }),
}));

vi.mock("./cart-merge", () => ({
  mergeGuestCartIntoAccount: mocks.mergeGuestCartIntoAccount,
}));

function session(userId: string, token = `token-${userId}`): CustomerSession {
  return { access_token: token, user: { id: userId } } as CustomerSession;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.resetModules();
  mocks.getSession.mockReset();
  mocks.onAuthStateChange.mockReset();
  mocks.unsubscribe.mockReset();
  mocks.mergeGuestCartIntoAccount.mockReset();
  delete window.__VERGEO_E2E_SESSION__;
});

describe("Customer reactive session barrier", () => {
  it("subscribes before getSession and keeps SIGNED_IN unpublished until merge completes", async () => {
    const merge = deferred<void>();
    let authCallback!: (event: string, value: CustomerSession | null) => void;
    mocks.onAuthStateChange.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
    });
    mocks.getSession.mockResolvedValue({ data: { session: null }, error: null });
    mocks.mergeGuestCartIntoAccount.mockReturnValue(merge.promise);
    const module = await import("./customer-session");

    await module.initializeCustomerSession();
    expect(mocks.onAuthStateChange.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.getSession.mock.invocationCallOrder[0]!,
    );
    expect(authCallback("SIGNED_IN", session("customer"))).toBeUndefined();
    const navigation = module.getReadyCustomerSession();
    expect(module.customerAuth.snapshot()).toMatchObject({ session: null, loading: true });

    merge.resolve();
    await expect(navigation).resolves.toMatchObject({ access_token: "token-customer" });
  });

  it("does not let a late getSession snapshot replace a newer auth event", async () => {
    const initial = deferred<{ data: { session: CustomerSession | null }; error: null }>();
    let authCallback!: (event: string, value: CustomerSession | null) => void;
    mocks.onAuthStateChange.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
    });
    mocks.getSession.mockReturnValue(initial.promise);
    mocks.mergeGuestCartIntoAccount.mockResolvedValue(undefined);
    const module = await import("./customer-session");
    const initialization = module.initializeCustomerSession();

    await vi.waitFor(() => expect(mocks.onAuthStateChange).toHaveBeenCalledOnce());
    authCallback("SIGNED_IN", session("new-account"));
    initial.resolve({ data: { session: session("old-account") }, error: null });
    await initialization;
    await module.getReadyCustomerSession();

    expect(mocks.mergeGuestCartIntoAccount).toHaveBeenCalledTimes(1);
    expect(module.customerAuth.snapshot().session?.user.id).toBe("new-account");
  });

  it("surfaces merge failure and retries without publishing early", async () => {
    const current = session("customer");
    let authCallback!: (event: string, value: CustomerSession | null) => void;
    mocks.onAuthStateChange.mockImplementation((callback) => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
    });
    mocks.getSession.mockResolvedValue({ data: { session: null }, error: null });
    mocks.mergeGuestCartIntoAccount
      .mockRejectedValueOnce(new Error("merge failed"))
      .mockResolvedValueOnce(undefined);
    const module = await import("./customer-session");
    await module.initializeCustomerSession();
    authCallback("SIGNED_IN", current);

    await expect(module.getReadyCustomerSession()).rejects.toThrow("merge failed");
    expect(module.customerAuth.snapshot().session).toBeNull();
    await expect(module.getReadyCustomerSession(true)).resolves.toBe(current);
    expect(mocks.mergeGuestCartIntoAccount).toHaveBeenCalledTimes(2);
  });
});
