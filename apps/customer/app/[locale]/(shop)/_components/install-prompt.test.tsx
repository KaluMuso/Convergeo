// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import commonMessages from "../../../../../../packages/i18n/messages/en/common.json";

import InstallPrompt, {
  INSTALL_DISMISS_KEY,
  INSTALL_REPROMPT_MS,
  promptSkipWaiting,
  shouldShowInstallPrompt,
} from "./install-prompt";

const install = commonMessages.install;

afterEach(cleanup);
beforeEach(() => {
  window.localStorage.clear();
});

function renderPrompt() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ common: commonMessages }} onError={() => {}}>
      <InstallPrompt />
    </NextIntlClientProvider>,
  );
}

function fireBeforeInstall() {
  const event = new Event("beforeinstallprompt");
  Object.assign(event, {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome: "accepted" as const }),
  });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

describe("install prompt frequency cap", () => {
  it("shows when never dismissed", () => {
    expect(shouldShowInstallPrompt(null, Date.now())).toBe(true);
  });

  it("suppresses within the re-prompt window, re-shows after it", () => {
    const now = 1_000_000_000_000;
    expect(shouldShowInstallPrompt(now - 1000, now)).toBe(false);
    expect(shouldShowInstallPrompt(now - INSTALL_REPROMPT_MS - 1, now)).toBe(true);
  });
});

describe("install prompt component", () => {
  it("appears on beforeinstallprompt and dismiss caps re-prompts", async () => {
    const user = userEvent.setup();
    renderPrompt();
    expect(screen.queryByText(install.title)).not.toBeInTheDocument();

    fireBeforeInstall();
    expect(await screen.findByText(install.title)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: install.dismiss }));
    expect(screen.queryByText(install.title)).not.toBeInTheDocument();
    expect(window.localStorage.getItem(INSTALL_DISMISS_KEY)).not.toBeNull();
  });

  it("stays hidden when dismissed recently (frequency-capped, no nag)", () => {
    window.localStorage.setItem(INSTALL_DISMISS_KEY, String(Date.now()));
    renderPrompt();
    fireBeforeInstall();
    expect(screen.queryByText(install.title)).not.toBeInTheDocument();
  });
});

describe("safe SW update handshake", () => {
  it("posts SKIP_WAITING to the waiting worker (user-triggered, not silent)", () => {
    const postMessage = vi.fn();
    const registration = {
      waiting: { postMessage },
    } as unknown as ServiceWorkerRegistration;
    promptSkipWaiting(registration);
    expect(postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
  });

  it("no-ops when there is no waiting worker", () => {
    const registration = { waiting: null } as unknown as ServiceWorkerRegistration;
    expect(() => promptSkipWaiting(registration)).not.toThrow();
  });
});
