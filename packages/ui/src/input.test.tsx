// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Input } from "./input";

describe("Input", () => {
  it("sets aria-invalid when error is true", () => {
    render(<Input error aria-label="field.email" />);
    expect(screen.getByRole("textbox", { name: "field.email" })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("supports uncontrolled usage", async () => {
    const user = userEvent.setup();

    render(<Input defaultValue="alpha" aria-label="field.name" />);
    const input = screen.getByRole("textbox", { name: "field.name" });
    expect(input).toHaveValue("alpha");

    await user.clear(input);
    await user.type(input, "beta");
    expect(input).toHaveValue("beta");
  });

  it("supports controlled usage", () => {
    render(<Input value="gamma" onChange={() => undefined} aria-label="field.name" />);
    expect(screen.getByRole("textbox", { name: "field.name" })).toHaveValue("gamma");
  });
});
