// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SupportInbox } from "./SupportInbox";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("next-intl", () => ({ useTranslations: (ns: string) => (key: string) => `${ns}.${key}` }));
vi.mock("./api", () => ({ supportApi: { request: mocks.request } }));
vi.mock("./ContextCard", () => ({ ContextCardView: () => null }));
vi.mock("./InteractionLog", () => ({ InteractionLog: () => null }));
vi.mock("./ReplyComposer", () => ({ ReplyComposer: () => null }));
vi.mock("../../../../lib/access-token", () => ({ getBrowserAccessToken: async () => "t" }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;

function setInputValue(el: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  mocks.request.mockReset();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("SupportInbox", () => {
  it("shows empty state when lookup returns no matches", async () => {
    mocks.request.mockResolvedValue({ matches: [] });
    await act(async () => root.render(<SupportInbox locale="en" />));
    await act(async () => {
      setInputValue(host.querySelector("input")!, "+260970000000");
      (host.querySelector("form") as HTMLFormElement).requestSubmit();
    });
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="support-inbox-empty"]')).toBeTruthy(),
    );
    expect(host.textContent).toContain("admin.boards.states.support.emptyTitle");
  });
});
