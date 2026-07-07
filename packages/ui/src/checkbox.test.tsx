// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { Checkbox } from "./checkbox";

describe("Checkbox", () => {
  it("toggles with click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<Checkbox id="terms" label="legal.acceptTerms" onChange={onChange} />);

    await user.click(screen.getByRole("checkbox", { name: "legal.acceptTerms" }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("toggles with Space keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<Checkbox id="terms" label="legal.acceptTerms" onChange={onChange} />);

    const checkbox = screen.getByRole("checkbox", { name: "legal.acceptTerms" });
    await user.tab();
    expect(checkbox).toHaveFocus();
    await user.keyboard(" ");
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
