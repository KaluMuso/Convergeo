// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Countdown, type CountdownLabels } from "./countdown";

const labels: CountdownLabels = {
  days: "d",
  hours: "h",
  minutes: "m",
  seconds: "s",
  expired: "Deal ended",
  ariaLabel: (time) => `Ends in ${time}`,
};

afterEach(cleanup);

describe("Countdown", () => {
  it("renders a live timer with the unit labels for a future target", async () => {
    const endsAt = new Date(Date.now() + 90_000).toISOString();
    render(<Countdown endsAt={endsAt} labels={labels} />);

    const timer = await screen.findByRole("timer");
    expect(timer).toBeInTheDocument();
    // Four unit blocks (days/hours/minutes/seconds).
    expect(timer).toHaveTextContent("d");
    expect(timer).toHaveTextContent("h");
    expect(timer).toHaveTextContent("m");
    expect(timer).toHaveTextContent("s");
    // Accessible summary reflects the remaining time.
    expect(timer).toHaveAttribute("aria-label", expect.stringContaining("Ends in"));
  });

  it("shows the expired label once the target is in the past", async () => {
    const endsAt = new Date(Date.now() - 1000).toISOString();
    render(<Countdown endsAt={endsAt} labels={labels} />);
    expect(await screen.findByText("Deal ended")).toBeInTheDocument();
  });
});
