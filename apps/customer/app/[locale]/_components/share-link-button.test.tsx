// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider } from "@vergeo/ui/src/toast";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShareLinkButton } from "./share-link-button";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ShareLinkButton", () => {
  it("copies the URL and confirms with a toast when native share is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(
      <ToastProvider copy={{ linkCopied: "Link copied", copyFailed: "Couldn't copy" }}>
        <ShareLinkButton label="Share" />
      </ToastProvider>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(await screen.findByText("Link copied")).toBeInTheDocument();
  });

  it("reports a copy failure as an error toast", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
    });
    render(
      <ToastProvider copy={{ linkCopied: "Link copied", copyFailed: "Couldn't copy" }}>
        <ShareLinkButton label="Share" />
      </ToastProvider>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't copy");
  });
});
