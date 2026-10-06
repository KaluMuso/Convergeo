// @vitest-environment jsdom

import { webcrypto } from "node:crypto";

import { ApiError } from "@vergeo/config";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReplyComposer } from "./ReplyComposer";

const mocks = vi.hoisted(() => ({
  actor: "admin-a",
  request: vi.fn(),
  apiForToken: vi.fn(),
}));

vi.mock("@vergeo/auth", () => ({
  getBrowserAccessToken: vi.fn(async () => mocks.actor),
}));
vi.mock("jose", () => ({ decodeJwt: (token: string) => ({ sub: token }) }));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
vi.mock("./api", () => ({
  CANNED_TEMPLATE_KEYS: ["delivery_eta", "pickup_ready"],
  supportApiForToken: (token: string) => {
    mocks.apiForToken(token);
    return { request: mocks.request };
  },
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
Object.defineProperty(globalThis, "crypto", { configurable: true, value: webcrypto });

const roots: ReturnType<typeof createRoot>[] = [];
const customerId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

function mount() {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  roots.push(root);
  act(() => root.render(<ReplyComposer customerId={customerId} orderId={null} onSent={vi.fn()} />));
  return { host, root };
}

function selectTemplate(host: HTMLElement, value: string) {
  act(() => {
    const select = host.querySelector("select")!;
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect((host.querySelector("section > button") as HTMLButtonElement).disabled).toBe(false);
}

async function send(host: HTMLElement) {
  const expectedCalls = mocks.request.mock.calls.length + 1;
  await act(async () => {
    const button = host.querySelector("section > button") as HTMLButtonElement;
    button.click();
    await vi.waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(expectedCalls));
  });
}

function sentBodies() {
  return mocks.request.mock.calls.map(([, init]) => JSON.parse(init.body as string));
}

beforeEach(() => {
  mocks.actor = "admin-a";
  mocks.request.mockReset();
  mocks.apiForToken.mockReset();
  sessionStorage.clear();
});

afterEach(() => {
  act(() => roots.forEach((root) => root.unmount()));
  roots.length = 0;
  document.body.innerHTML = "";
});

describe("support reply operation identity", () => {
  it("reuses an uncertain send across reload, then gives a confirmed new reply a new ID", async () => {
    mocks.request.mockRejectedValueOnce(new Error("network response lost"));
    mocks.request.mockResolvedValue({ channel: "sms", deduped: true });

    const first = mount();
    selectTemplate(first.host, "delivery_eta");
    await send(first.host);
    const firstId = sentBodies()[0].message_id;
    expect(firstId).toEqual(expect.any(String));
    expect(first.host.textContent).toContain("failure");
    const storedKeys = Object.keys(sessionStorage);
    expect(storedKeys).toHaveLength(1);
    expect(storedKeys[0]).not.toContain(customerId);
    expect(sessionStorage.getItem(storedKeys[0]!)).not.toContain(customerId);
    expect(sessionStorage.getItem(storedKeys[0]!)).not.toContain("delivery_eta");

    act(() => first.root.unmount());
    roots.splice(roots.indexOf(first.root), 1);
    const reloaded = mount();
    selectTemplate(reloaded.host, "delivery_eta");
    await send(reloaded.host);
    expect(sentBodies()[1].message_id).toBe(firstId);
    expect(Object.keys(sessionStorage)).toHaveLength(0);

    await send(reloaded.host);
    expect(sentBodies()[2].message_id).not.toBe(firstId);
  });

  it("does not carry an uncertain operation into another admin account", async () => {
    mocks.request.mockRejectedValueOnce(new Error("network response lost"));
    mocks.request.mockResolvedValue({ channel: "sms", deduped: false });
    const composer = mount();
    selectTemplate(composer.host, "delivery_eta");
    await send(composer.host);
    const firstId = sentBodies()[0].message_id;

    mocks.actor = "admin-b";
    await send(composer.host);
    expect(sentBodies()[1].message_id).not.toBe(firstId);
    expect(mocks.apiForToken.mock.calls.map(([token]) => token)).toEqual(["admin-a", "admin-b"]);
  });

  it("changes identity for edited content and blocks a second click while sending", async () => {
    let resolveRequest!: (value: unknown) => void;
    mocks.request.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );
    mocks.request.mockResolvedValue({ channel: "sms", deduped: false });
    const composer = mount();
    selectTemplate(composer.host, "delivery_eta");
    await act(async () => {
      const button = composer.host.querySelector("section > button") as HTMLButtonElement;
      button.click();
      button.click();
      await vi.waitFor(() => expect(mocks.request).toHaveBeenCalledTimes(1));
    });
    expect(mocks.request).toHaveBeenCalledTimes(1);
    await act(async () => resolveRequest({ channel: "sms", deduped: false }));

    selectTemplate(composer.host, "pickup_ready");
    await send(composer.host);
    expect(sentBodies()[1].message_id).not.toBe(sentBodies()[0].message_id);
  });

  it("gives another customer a separate operation after an uncertain response", async () => {
    mocks.request.mockRejectedValueOnce(new Error("network response lost"));
    mocks.request.mockResolvedValue({ channel: "sms", deduped: false });
    const composer = mount();
    selectTemplate(composer.host, "delivery_eta");
    await send(composer.host);
    const firstId = sentBodies()[0].message_id;

    const otherCustomer = "cccccccc-cccc-cccc-cccc-cccccccccccc";
    act(() =>
      composer.root.render(
        <ReplyComposer customerId={otherCustomer} orderId={null} onSent={vi.fn()} />,
      ),
    );
    await send(composer.host);
    expect(sentBodies()[1].message_id).not.toBe(firstId);
    expect(sentBodies()[1].customer_id).toBe(otherCustomer);
    expect(Object.keys(sessionStorage).join(" ")).not.toContain(otherCustomer);
  });

  it("requires an explicit new operation after a conflicting reuse", async () => {
    mocks.request.mockRejectedValueOnce(
      new ApiError("idempotency_conflict", "Reply identity conflicts", { status: 409 }),
    );
    mocks.request.mockResolvedValue({ channel: "sms", deduped: false });
    const composer = mount();
    selectTemplate(composer.host, "delivery_eta");
    await send(composer.host);
    const firstId = sentBodies()[0].message_id;
    expect(composer.host.textContent).toContain("conflict");
    expect((composer.host.querySelector("section > button") as HTMLButtonElement).disabled).toBe(
      true,
    );

    act(() => {
      [...composer.host.querySelectorAll("button")].at(-1)!.click();
    });
    expect(Object.keys(sessionStorage)).toHaveLength(0);
    await send(composer.host);
    expect(sentBodies()[1].message_id).not.toBe(firstId);
  });
});
