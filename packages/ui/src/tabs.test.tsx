// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { Tabs } from "./tabs";

afterEach(cleanup);

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

  it("lazily mounts only the active panel by default", () => {
    render(<Tabs items={items} ariaLabel="Product tabs" defaultValue="one" />);
    expect(screen.getByText("Panel One")).toBeVisible();
    // Inactive panels render an empty div — their content is not in the DOM.
    expect(screen.queryByText("Panel Two")).not.toBeInTheDocument();
    expect(screen.queryByText("Panel Three")).not.toBeInTheDocument();
  });

  it("mountInactivePanels keeps every panel's content in the DOM (SEO-safe)", () => {
    render(<Tabs items={items} ariaLabel="Product tabs" defaultValue="one" mountInactivePanels />);
    // All panels are present in the server-rendered DOM so crawlers see them,
    // even though the inactive ones are visually hidden.
    expect(screen.getByText("Panel One")).toBeVisible();
    expect(screen.getByText("Panel Two")).toBeInTheDocument();
    expect(screen.getByText("Panel Three")).toBeInTheDocument();
    expect(screen.getByText("Panel Two")).not.toBeVisible();

    const panels = screen.getAllByRole("tabpanel", { hidden: true });
    const inactive = panels.filter((panel) => panel.hasAttribute("hidden"));
    expect(inactive).toHaveLength(2);
  });
});
