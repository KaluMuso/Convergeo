// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { OtpField } from "./otp-field";

const digitLabel = (index: number) => `otp.digit.${index + 1}`;

describe("OtpField", () => {
  it("auto-advances on digit input", async () => {
    const user = userEvent.setup();

    render(<OtpField ariaLabel="otp.group" getDigitAriaLabel={digitLabel} />);

    const group = screen.getByRole("group", { name: "otp.group" });
    const inputs = within(group).getAllByRole("textbox");

    await user.click(inputs[0]!);
    await user.keyboard("1");
    expect(inputs[0]).toHaveValue("1");
    expect(inputs[1]).toHaveFocus();

    await user.keyboard("2");
    expect(inputs[1]).toHaveValue("2");
    expect(inputs[2]).toHaveFocus();
  });

  it("moves back on backspace", async () => {
    const user = userEvent.setup();

    render(<OtpField ariaLabel="otp.group" getDigitAriaLabel={digitLabel} defaultValue="123" />);

    const group = screen.getByRole("group", { name: "otp.group" });
    const inputs = within(group).getAllByRole("textbox");

    await user.click(inputs[2]!);
    await user.keyboard("{Backspace}");
    expect(inputs[2]).toHaveValue("");
    expect(inputs[2]).toHaveFocus();

    await user.keyboard("{Backspace}");
    expect(inputs[1]).toHaveValue("");
    expect(inputs[1]).toHaveFocus();
  });

  it("distributes pasted code across cells", async () => {
    const user = userEvent.setup();

    render(<OtpField ariaLabel="otp.group" getDigitAriaLabel={digitLabel} />);

    const group = screen.getByRole("group", { name: "otp.group" });
    const inputs = within(group).getAllByRole("textbox");

    await user.click(inputs[0]!);
    await user.paste("654321");

    inputs.forEach((input, index) => {
      expect(input).toHaveValue(String(6 - index));
    });
  });

  it("fires onComplete once when six digits are entered", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();

    render(
      <OtpField ariaLabel="otp.group" getDigitAriaLabel={digitLabel} onComplete={onComplete} />,
    );

    const group = screen.getByRole("group", { name: "otp.group" });
    const inputs = within(group).getAllByRole("textbox");

    await user.click(inputs[0]!);
    await user.paste("112233");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("112233");

    await user.click(inputs[5]!);
    await user.keyboard("{Backspace}");
    await user.keyboard("4");
    expect(onComplete).toHaveBeenCalledTimes(2);
    expect(onComplete).toHaveBeenLastCalledWith("112234");
  });

  it("exposes numeric input mode and one-time-code autocomplete", () => {
    render(<OtpField ariaLabel="otp.group" getDigitAriaLabel={digitLabel} />);

    const group = screen.getByRole("group", { name: "otp.group" });
    const inputs = within(group).getAllByRole("textbox");

    expect(inputs[0]).toHaveAttribute("inputmode", "numeric");
    expect(inputs[0]).toHaveAttribute("autocomplete", "one-time-code");
    expect(inputs[1]).toHaveAttribute("autocomplete", "off");
  });
});
