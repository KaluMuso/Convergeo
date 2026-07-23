// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { orderStatusTone, StatusChip } from "./status-chip";

afterEach(cleanup);

describe("StatusChip", () => {
  it("renders the label with the tone recipe and data attribute", () => {
    render(<StatusChip tone="success" label="Completed" />);
    const chip = screen.getByText("Completed");
    expect(chip).toHaveAttribute("data-tone", "success");
    expect(chip).toHaveClass("text-success", "border-success");
  });

  it("uses the neutral recipe for the neutral tone", () => {
    render(<StatusChip tone="neutral" label="Unknown" />);
    expect(screen.getByText("Unknown")).toHaveClass("text-text-2");
  });
});

describe("orderStatusTone", () => {
  it("maps the order lifecycle to traffic-light tones", () => {
    expect(orderStatusTone("placed")).toBe("warning");
    expect(orderStatusTone("confirmed")).toBe("info");
    expect(orderStatusTone("processing")).toBe("info");
    expect(orderStatusTone("delivered")).toBe("success");
    expect(orderStatusTone("completed")).toBe("success");
    expect(orderStatusTone("cancelled")).toBe("danger");
  });

  it("degrades unknown/empty statuses to neutral", () => {
    expect(orderStatusTone("archived")).toBe("neutral");
    expect(orderStatusTone("")).toBe("neutral");
  });
});
