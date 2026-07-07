// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Badge } from "./badge";
import { EventCard } from "./event-card";

const LONG_BEMBA_TITLE =
  "Icibilisha ca kusefya icaletelela abantu abalinga ukutandalila imilimo ya bukolwe";

describe("EventCard", () => {
  afterEach(() => {
    cleanup();
  });

  const baseProps = {
    title: "Lusaka Jazz Night",
    dateLabel: "Sat 12 Jul · 19:00",
    venueLabel: "East Park Mall, Lusaka",
    spotsFilled: 75,
    spotsTotal: 100,
    capacityLabel: "75 / 100 spots filled",
    ctaLabel: "Get ticket",
    ngwee: 15000,
  };

  it("renders required fields with capacity bar", () => {
    render(
      <EventCard {...baseProps} badge={<Badge variant="selling_fast" label="Selling fast" />} />,
    );
    expect(screen.getByTestId("event-card")).toBeInTheDocument();
    expect(screen.getByTestId("spots-fill")).toHaveStyle({ width: "75%" });
    expect(screen.getByText("K150.00")).toBeInTheDocument();
  });

  it("renders free label when isFree", () => {
    render(<EventCard {...baseProps} isFree freeLabel="Free entry" ngwee={undefined} />);
    expect(screen.getByTestId("event-free-label")).toHaveTextContent("Free entry");
  });

  it("renders skeleton variant", () => {
    render(<EventCard {...baseProps} skeleton />);
    expect(screen.getByTestId("event-card-skeleton")).toBeInTheDocument();
  });

  it("truncates long Bemba title", () => {
    render(<EventCard {...baseProps} title={LONG_BEMBA_TITLE} />);
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveStyle({ WebkitLineClamp: 2, overflow: "hidden" });
  });

  it("fires CTA callback", async () => {
    const user = userEvent.setup();
    const onCtaClick = vi.fn();
    render(<EventCard {...baseProps} onCtaClick={onCtaClick} />);
    await user.click(screen.getByTestId("event-card-cta"));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });
});
