// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_SW_URL,
  registerServiceWorkerIfAvailable,
  ServiceWorkerRegister,
  shouldRegisterServiceWorker,
} from "./service-worker-register";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("shouldRegisterServiceWorker", () => {
  it("returns true when /sw.js is present as JavaScript", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/javascript; charset=utf-8" },
    });

    await expect(shouldRegisterServiceWorker(DEFAULT_SW_URL, fetchImpl)).resolves.toBe(true);
    expect(fetchImpl).toHaveBeenCalledWith(
      DEFAULT_SW_URL,
      expect.objectContaining({ method: "HEAD" }),
    );
  });

  it("returns false when /sw.js is missing (404)", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: { get: () => "text/html" },
    });

    await expect(shouldRegisterServiceWorker(DEFAULT_SW_URL, fetchImpl)).resolves.toBe(false);
  });
});

describe("registerServiceWorkerIfAvailable", () => {
  it("skips registration when the worker is unavailable", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: { get: () => null },
    });
    const registerImpl = vi.fn();

    await expect(
      registerServiceWorkerIfAvailable(DEFAULT_SW_URL, { fetchImpl, registerImpl }),
    ).resolves.toBe("skipped");
    expect(registerImpl).not.toHaveBeenCalled();
  });

  it("registers only after a successful probe", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/javascript" },
    });
    const registerImpl = vi.fn().mockResolvedValue(undefined);

    await expect(
      registerServiceWorkerIfAvailable(DEFAULT_SW_URL, { fetchImpl, registerImpl }),
    ).resolves.toBe("registered");
    expect(registerImpl).toHaveBeenCalledWith(DEFAULT_SW_URL);
  });
});

describe("ServiceWorkerRegister", () => {
  it("does not call serviceWorker.register when /sw.js 404s", async () => {
    const register = vi.fn();
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { register },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        headers: { get: () => null },
      }),
    );

    render(<ServiceWorkerRegister />);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    expect(register).not.toHaveBeenCalled();
  });
});
