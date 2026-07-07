// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Stepper } from "./stepper";

const steps = [
  { key: "items", label: "Items" },
  { key: "delivery", label: "Delivery" },
  { key: "pay", label: "Pay" },
  { key: "review", label: "Review" },
];

describe("Stepper", () => {
  it("renders done, current, and upcoming states", () => {
    render(
      <Stepper
        steps={steps}
        currentStep={1}
        doneIndicator={<span data-testid="done-icon">D</span>}
        stepAnnouncement={(current, total) => `step ${current} of ${total}`}
      />,
    );

    expect(screen.getByTestId("done-icon")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Delivery")).toHaveClass("text-primary");
    expect(screen.getByText("Review")).toHaveClass("text-text-3");
  });

  it("announces step position for screen readers", () => {
    const { container } = render(
      <Stepper
        steps={steps}
        currentStep={1}
        doneIndicator={<span>D</span>}
        stepAnnouncement={(current, total) => `step ${current} of ${total}`}
      />,
    );
    const announcement = container.querySelector(".sr-only");
    expect(announcement).toHaveTextContent("step 2 of 4");
  });
});
