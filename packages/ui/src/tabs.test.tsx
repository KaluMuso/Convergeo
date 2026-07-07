// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Tabs } from "./tabs";

const items = [
  { key: "one", label: "Tab One", panel: <div>Panel One</div> },
  { key: "two", label: "Tab Two", panel: <div>Panel Two</div> },
  { key: "three", label: "Tab Three", panel: <div>Panel Three</div> },
];

describe("Tabs", () => {
  it("marks the active tab with aria-selected", () => {
    render(<Tabs items={items} ariaLabel="Product tabs" defaultValue="one" />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
  });

  it("supports arrow-key roving focus and selection", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <Tabs items={items} ariaLabel="Product tabs" defaultValue="one" />,
    );

    const tablist = container.querySelector('[role="tablist"]') as HTMLElement;
    const tabs = within(tablist).getAllByRole("tab");
    tabs[0]!.focus();
    expect(tabs[0]).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(tabs[1]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel Two")).toBeVisible();
  });
});
