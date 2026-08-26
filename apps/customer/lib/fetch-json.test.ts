import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_FETCH_TIMEOUT_MS, FetchHttpError, fetchJson } from "./fetch-json";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetchJson", () => {
  it("1. successful fetch performs one attempt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchJson<{ ok: boolean }>("https://api.example.test/catalog")).resolves.toEqual({
      ok: true,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("2. HTTP 400 does NOT retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: "bad" }, 400));
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retryDelayMs: 0 });
    await expect(promise).rejects.toBeInstanceOf(FetchHttpError);
    await expect(promise).rejects.toMatchObject({ status: 400 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("3. HTTP 401 does NOT retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: "unauthorized" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retryDelayMs: 0 });
    await expect(promise).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("4. HTTP 404 does NOT retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: "missing" }, 404));
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retryDelayMs: 0 });
    await expect(promise).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("5. HTTP 429 is treated as a no-retry 4xx (no documented exception for this app)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ error: "rate limited" }, 429));
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retryDelayMs: 0 });
    await expect(promise).rejects.toMatchObject({ status: 429 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("6. HTTP 500 retries and can recover", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("nope", { status: 500 }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchJson<{ items: unknown[] }>("https://api.example.test/catalog", { retryDelayMs: 0 }),
    ).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("7. HTTP 503 retries and then fails after budget", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("down", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retryDelayMs: 0 });
    await expect(promise).rejects.toMatchObject({ status: 503 });
    // default retries=1 -> 2 total attempts (initial + 1 retry), then throw.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("8. network error retries and can recover", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network down"))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchJson<{ items: unknown[] }>("https://api.example.test/catalog", { retryDelayMs: 0 }),
    ).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("9. internal timeout aborts the individual attempt and retries", async () => {
    vi.useFakeTimers();
    let call = 0;
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      call += 1;
      if (call === 1) {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(init.signal!.reason);
          });
        });
      }
      return Promise.resolve(jsonResponse({ items: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson<{ items: unknown[] }>("https://api.example.test/catalog", {
      timeoutMs: 100,
      retryDelayMs: 0,
    });

    // Drains the first attempt's timeout AND the (0ms) retry-delay timer it
    // schedules next — a fixed single advance can race the retry timer being
    // scheduled only after the abort's rejection microtask settles.
    await vi.runAllTimersAsync();

    await expect(promise).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("10. repeated timeout exhausts retry budget and fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(init.signal!.reason);
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", {
      timeoutMs: 100,
      retryDelayMs: 0,
    });
    // Swallow the eventual rejection reason so an unhandled-rejection isn't
    // observed before the assertion below attaches its own handler.
    promise.catch(() => {});

    await vi.runAllTimersAsync();

    await expect(promise).rejects.toMatchObject({ name: "TimeoutError" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("11. caller AbortSignal abort does NOT retry", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        if (init?.signal?.aborted) {
          reject(init.signal.reason);
          return;
        }
        init?.signal?.addEventListener("abort", () => {
          reject(init.signal!.reason);
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    controller.abort(new DOMException("Caller cancelled", "AbortError"));

    const promise = fetchJson("https://api.example.test/catalog", {
      signal: controller.signal,
      retryDelayMs: 0,
    });

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("12. caller signal + internal timeout signal can coexist on a normal success", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchJson<{ ok: boolean }>("https://api.example.test/catalog", {
        signal: controller.signal,
        timeoutMs: 5_000,
      }),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Both signals were live and unaborted throughout — neither interfered.
    expect(controller.signal.aborted).toBe(false);
  });

  it("13. timeoutMs=0 disables the internal timeout", async () => {
    vi.useFakeTimers();
    let resolveFetch!: (response: Response) => void;
    const fetchMock = vi.fn().mockImplementation(() => {
      return new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson<{ ok: boolean }>("https://api.example.test/catalog", {
      timeoutMs: 0,
    });

    // Advance far past any plausible timeout — with timeoutMs=0 nothing aborts.
    await vi.advanceTimersByTimeAsync(60_000);
    resolveFetch(jsonResponse({ ok: true }));

    await expect(promise).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("14. timeout handles are cleaned up (no orphan timers) on success, HTTP retry, and abort", async () => {
    vi.useFakeTimers();

    // Success path.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ok: true })));
    await fetchJson("https://api.example.test/a", { timeoutMs: 100 });
    expect(vi.getTimerCount()).toBe(0);

    // 5xx-retry path.
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("nope", { status: 500 }))
        .mockResolvedValueOnce(jsonResponse({ ok: true })),
    );
    const retryPromise = fetchJson("https://api.example.test/b", {
      timeoutMs: 100,
      retryDelayMs: 10,
    });
    await vi.advanceTimersByTimeAsync(10);
    await retryPromise;
    expect(vi.getTimerCount()).toBe(0);

    // Caller-abort path.
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
        });
      }),
    );
    const abortPromise = fetchJson("https://api.example.test/c", {
      signal: controller.signal,
      timeoutMs: 100,
    });
    abortPromise.catch(() => {});
    controller.abort(new DOMException("cancelled", "AbortError"));
    await expect(abortPromise).rejects.toMatchObject({ name: "AbortError" });
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("DEFAULT_FETCH_TIMEOUT_MS", () => {
  it("is applied when timeoutMs is not supplied", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const promise = fetchJson("https://api.example.test/catalog", { retries: 0 });
    promise.catch(() => {});

    // One tick short of the default timeout: still pending.
    await vi.advanceTimersByTimeAsync(DEFAULT_FETCH_TIMEOUT_MS - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1);
    await expect(promise).rejects.toMatchObject({ name: "TimeoutError" });
  });
});
