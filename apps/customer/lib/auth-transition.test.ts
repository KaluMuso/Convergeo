import { describe, expect, it, vi } from "vitest";

import { AuthTransition, type CartMergeResolution, type CustomerSession } from "./auth-transition";

function session(userId: string, token = `token-${userId}`): CustomerSession {
  return { access_token: token, user: { id: userId } } as CustomerSession;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("AuthTransition", () => {
  it("uses one pending barrier for SIGNED_IN and navigation", async () => {
    const merge = deferred<void>();
    const reconcile = vi.fn(() => merge.promise);
    const transition = new AuthTransition(reconcile);
    const signedIn = transition.observe(session("customer"));
    const navigation = transition.ready();

    expect(transition.snapshot()).toMatchObject({ session: null, loading: true });
    await vi.waitFor(() => expect(reconcile).toHaveBeenCalledOnce());
    merge.resolve();
    await Promise.all([signedIn, navigation]);
    expect(transition.snapshot().session?.user.id).toBe("customer");
  });

  it("keeps the session unpublished after failure and retries with a resolution", async () => {
    const resolution: CartMergeResolution = {
      accept_price_changes: ["listing"],
      accepted_price_proposals: { listing: "signed-price-terms" },
      pickup_location_choices: {},
      remove_listing_ids: [],
    };
    const reconcile = vi
      .fn()
      .mockRejectedValueOnce(new Error("merge failed"))
      .mockResolvedValueOnce(undefined);
    const transition = new AuthTransition(reconcile);

    await expect(transition.observe(session("customer"))).rejects.toThrow("merge failed");
    expect(transition.snapshot()).toMatchObject({ session: null, loading: false });
    await transition.ready(true, resolution);
    expect(reconcile).toHaveBeenLastCalledWith(expect.anything(), resolution);
    expect(transition.snapshot().session?.user.id).toBe("customer");
  });

  it("fences an old account when a new identity arrives", async () => {
    const first = deferred<void>();
    const reconcile = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValueOnce(undefined);
    const transition = new AuthTransition(reconcile);
    const accountA = transition.observe(session("account-a"));
    const accountB = transition.observe(session("account-b"));

    first.resolve();
    await expect(accountA).rejects.toThrow("auth.transition_changed");
    await accountB;
    expect(transition.snapshot().session?.user.id).toBe("account-b");
  });

  it("logout cannot be undone by a late merge completion", async () => {
    const merge = deferred<void>();
    const transition = new AuthTransition(() => merge.promise);
    const signedIn = transition.observe(session("customer"));
    await transition.observe(null);
    merge.resolve();

    await expect(signedIn).rejects.toThrow("auth.transition_changed");
    expect(transition.snapshot()).toMatchObject({ session: null, loading: false, error: null });
  });

  it("publishes a refreshed token without re-running the merge", async () => {
    const reconcile = vi.fn().mockResolvedValue(undefined);
    const transition = new AuthTransition(reconcile);
    await transition.observe(session("customer", "old"));
    await transition.observe(session("customer", "new"));

    expect(reconcile).toHaveBeenCalledOnce();
    expect(transition.snapshot().session?.access_token).toBe("new");
  });
});
