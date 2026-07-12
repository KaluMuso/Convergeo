// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import commonMessages from "../../../../../packages/i18n/messages/en/common.json";

import OfflinePage from "./page";

const offline = commonMessages.offline;

afterEach(cleanup);

function renderOffline() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ common: commonMessages }} onError={() => {}}>
      <OfflinePage />
    </NextIntlClientProvider>,
  );
}

describe("offline fallback page", () => {
  it("renders honest branded offline copy with recovery affordances", () => {
    renderOffline();
    expect(screen.getByText(offline.heading)).toBeInTheDocument();
    // Honest messaging: previously viewed pages still work, no fake success.
    expect(screen.getByText(offline.body)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: offline.retry })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: offline.home })).toHaveAttribute("href", "/en");
  });

  it("retry reloads the page (recover when connectivity returns)", async () => {
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, reload },
      writable: true,
    });
    const user = userEvent.setup();
    renderOffline();
    await user.click(screen.getByRole("button", { name: offline.retry }));
    expect(reload).toHaveBeenCalled();
  });
});
