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
  it("opens WhatsApp fallback when native share is unavailable", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    render(<ShareLinkButton label="Share" text="Phone from K99" url="https://x.test/p/a" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(open).toHaveBeenCalledWith(
      expect.stringContaining("https://wa.me/?text="),
      "_blank",
      "noopener,noreferrer",
    );
    const href = open.mock.calls[0]?.[0] as string;
    expect(decodeURIComponent(href)).toContain("Phone from K99");
    expect(decodeURIComponent(href)).toContain("https://x.test/p/a");
  });

  it("uses native share when available", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "share", {
      value: share,
      configurable: true,
    });
    render(<ShareLinkButton label="Share" title="T" text="Line" url="https://x.test/p/b" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(share).toHaveBeenCalledWith({
      title: "T",
      text: "Line",
      url: "https://x.test/p/b",
    });
  });

  it("ignores AbortError from native share", async () => {
    const share = vi.fn().mockRejectedValue(new DOMException("cancelled", "AbortError"));
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    Object.defineProperty(window.navigator, "share", {
      value: share,
      configurable: true,
    });
    render(<ShareLinkButton label="Share" url="https://x.test" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(open).not.toHaveBeenCalled();
  });

  it("copies the URL when WhatsApp window cannot open", async () => {
    Object.defineProperty(window.navigator, "share", {
      value: undefined,
      configurable: true,
    });
    vi.spyOn(window, "open").mockReturnValue(null);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(
      <ToastProvider copy={{ linkCopied: "Link copied", copyFailed: "Couldn't copy" }}>
        <ShareLinkButton label="Share" url="https://x.test/p/c" />
      </ToastProvider>,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Share" }));
    });
    expect(writeText).toHaveBeenCalledWith("https://x.test/p/c");
    expect(await screen.findByText("Link copied")).toBeInTheDocument();
  });
});
