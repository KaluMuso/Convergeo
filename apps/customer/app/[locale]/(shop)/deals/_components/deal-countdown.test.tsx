// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DealCountdown } from "./deal-countdown";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("DealCountdown", () => {
  it("counts down against server time and shows Ended at zero", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-09T10:00:00Z"));
    render(
      <DealCountdown
        endsAt="2026-11-09T10:00:03Z"
        serverTime="2026-11-09T10:00:00Z"
        template="Ends in {time}"
        endedLabel="Ended"
      />,
    );
    expect(screen.getByTestId("deal-countdown")).toHaveTextContent(
      "Ends in 00:03",
    );
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.getByTestId("deal-countdown")).toHaveTextContent("Ended");
  });
});
