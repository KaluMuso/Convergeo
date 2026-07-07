// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { Switch } from "./switch";

describe("Switch", () => {
  it("toggles with click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<Switch id="notifications" label="account.notifications" onChange={onChange} />);

    const toggle = screen.getByRole("switch", { name: "account.notifications" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("toggles with Space keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<Switch id="notifications" label="account.notifications" onChange={onChange} />);

    const toggle = screen.getByRole("switch", { name: "account.notifications" });
    await user.tab();
    expect(toggle).toHaveFocus();
    await user.keyboard(" ");
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
