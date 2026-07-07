// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { FormField } from "./form-field";
import { Input } from "./input";

describe("FormField", () => {
  it("associates label, help text, and error via describedby", () => {
    render(
      <FormField
        id="email"
        label="field.email.label"
        helpText="field.email.help"
        errorMessage="field.email.error"
        required
        requiredMarker="*"
      >
        <Input placeholder="field.email.placeholder" />
      </FormField>,
    );

    const input = screen.getByRole("textbox");
    const label = screen.getByText("field.email.label");
    const help = screen.getByText("field.email.help");
    const error = screen.getByText("field.email.error");

    expect(label).toHaveAttribute("for", "email");
    expect(input).toHaveAttribute("id", "email");
    expect(input).toHaveAttribute("aria-describedby", "email-help email-error");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-required", "true");
    expect(help).toHaveAttribute("id", "email-help");
    expect(error).toHaveAttribute("id", "email-error");
    expect(error).toHaveAttribute("role", "alert");
  });

  it("wires help-only describedby when no error", () => {
    render(
      <FormField id="phone" label="field.phone.label" helpText="field.phone.help">
        <Input aria-label="field.phone.label" />
      </FormField>,
    );

    const input = screen.getByLabelText("field.phone.label");
    expect(input).toHaveAttribute("aria-describedby", "phone-help");
    expect(input).not.toHaveAttribute("aria-invalid", "true");
  });
});
