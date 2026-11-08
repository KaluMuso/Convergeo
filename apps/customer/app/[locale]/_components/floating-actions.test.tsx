// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({ pathname: "/en", push: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push }),
}));

import { FloatingActions, isHomePath } from "./floating-actions";

const labels = {
  ask: "Ask Vergeo",
  askTitle: "Ask Vergeo",
  askHint: "Describe what you need",
  askPlaceholder: "e.g. solar panel",
  send: "Ask",
  voiceStart: "Speak your question",
  voiceStop: "Stop listening",
  listening: "Listening…",
  voiceUnsupported: "Voice input isn't supported",
  close: "Close",
  showFooter: "Show site links",
  hideFooter: "Hide site links",
};

afterEach(() => {
  cleanup();
  nav.push.mockReset();
  delete (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
});

describe("FloatingActions", () => {
  it("hides the footer on home and opens it as a sheet from the toggle", () => {
    nav.pathname = "/en";
    render(<FloatingActions locale="en" labels={labels} footer={<footer>Site links</footer>} />);
    expect(screen.getByTestId("footer-sheet")).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Show site links" }));
    expect(screen.getByTestId("footer-sheet")).toBeVisible();
    expect(screen.getByRole("button", { name: "Hide site links" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("renders the footer inline and no toggle on other pages", () => {
    nav.pathname = "/en/p/solar-panel";
    render(<FloatingActions locale="en" labels={labels} footer={<footer>Site links</footer>} />);
    expect(screen.getByText("Site links")).toBeVisible();
    expect(screen.queryByTestId("fab-footer-toggle")).not.toBeInTheDocument();
    // Product pages raise the stack above the sticky add-to-cart bar.
    expect(screen.getByTestId("floating-actions")).toHaveClass("v-fab-stack--raised");
  });

  it("sends the typed question to Ask Vergeo", () => {
    nav.pathname = "/en/c/all";
    render(<FloatingActions locale="en" labels={labels} footer={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask Vergeo" }));
    fireEvent.change(screen.getByTestId("fab-ask-input"), { target: { value: "solar panel" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(nav.push).toHaveBeenCalledWith("/en/ask?q=solar%20panel");
  });

  it("offers dictation only where the Web Speech API exists", () => {
    nav.pathname = "/en/c/all";
    const start = vi.fn();
    class FakeRecognition {
      lang = "";
      interimResults = false;
      continuous = false;
      onresult = null;
      onend = null;
      onerror = null;
      start = start;
      stop = vi.fn();
    }
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition =
      FakeRecognition;
    render(<FloatingActions locale="en" labels={labels} footer={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask Vergeo" }));
    fireEvent.click(screen.getByRole("button", { name: "Speak your question" }));
    expect(start).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("explains when voice input is unavailable", () => {
    nav.pathname = "/en/c/all";
    render(<FloatingActions locale="en" labels={labels} footer={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask Vergeo" }));
    expect(screen.getByTestId("fab-voice-unsupported")).toBeInTheDocument();
  });

  it("detects the home path", () => {
    expect(isHomePath("/en", "en")).toBe(true);
    expect(isHomePath("/en/", "en")).toBe(true);
    expect(isHomePath("/en/search", "en")).toBe(false);
  });
});
