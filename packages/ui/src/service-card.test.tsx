// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ServiceCard } from "./service-card";

const LONG_NYANJA_TITLE =
  "Ntchito yosamalira malo osungira zinthu ndi yofunikira kwambiri mu mzinda wa Lusaka";

describe("ServiceCard", () => {
  afterEach(() => {
    cleanup();
  });

  const baseProps = {
    title: "Home Cleaning",
    providerLabel: "Sparkle Pro",
    rating: 4.8,
    reviewCount: 42,
    reviewCountLabel: "(42)",
    ctaLabel: "Book now",
    fromNgwee: 35000,
    fromPriceLabel: "From",
    tags: [{ label: "Same day", color: "#7AAB8A" }],
  };

  it("renders required fields with tag pills and from price", () => {
    render(<ServiceCard {...baseProps} />);
    expect(screen.getByTestId("service-card")).toBeInTheDocument();
    expect(screen.getByText("Home Cleaning")).toBeInTheDocument();
    expect(screen.getByText("From")).toBeInTheDocument();
    expect(screen.getByText("K350.00")).toBeInTheDocument();
    expect(screen.getByTestId("pill")).toHaveTextContent("Same day");
  });

  it("renders skeleton variant", () => {
    render(<ServiceCard {...baseProps} skeleton />);
    expect(screen.getByTestId("service-card-skeleton")).toBeInTheDocument();
  });

  it("truncates long Nyanja title", () => {
    render(<ServiceCard {...baseProps} title={LONG_NYANJA_TITLE} />);
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveStyle({ WebkitLineClamp: 2, overflow: "hidden" });
  });

  it("fires CTA callback", async () => {
    const user = userEvent.setup();
    const onCtaClick = vi.fn();
    render(<ServiceCard {...baseProps} onCtaClick={onCtaClick} />);
    await user.click(screen.getByTestId("service-card-cta"));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });
});
