// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { Button } from "./button";

describe("Button", () => {
  it("fires onClick when clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <Button loadingLabel="loading.action" onClick={onClick}>
        action.submit
      </Button>,
    );

    await user.click(screen.getByRole("button", { name: "action.submit" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick when disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <Button loadingLabel="loading.action" disabled onClick={onClick}>
        action.submit
      </Button>,
    );

    await user.click(screen.getByRole("button", { name: "action.submit" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("suppresses click and sets aria-busy when loading", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <Button loading loadingLabel="loading.action" onClick={onClick}>
        action.submit
      </Button>,
    );

    const button = screen.getByRole("button", { name: "loading.action" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();

    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("is keyboard operable with Enter and Space", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <Button loadingLabel="loading.action" onClick={onClick}>
        action.submit
      </Button>,
    );

    await user.tab();
    const button = screen.getByRole("button", { name: "action.submit" });
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
