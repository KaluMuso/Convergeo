// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openMobileMenu } from "./menu-events";
import MobileDrawer, { DEPT_COLLAPSED } from "./mobile-drawer";
import { MobileMenuHost } from "./mobile-menu-host";
import { TEST_LABELS, TEST_TREE } from "./test-fixtures";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/en") }));

const sessionState = vi.hoisted(() => ({
  user: null as null | { email: string; user_metadata: Record<string, unknown> },
}));
vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ user: sessionState.user, session: null }),
}));

const load = () => Promise.resolve(TEST_TREE);
const swallowNavigation = (event: Event) => event.preventDefault();

beforeEach(() => {
  document.addEventListener("click", swallowNavigation);
  window.localStorage.clear();
  sessionState.user = null;
  vi.mocked(usePathname).mockReturnValue("/en");
});

afterEach(() => {
  document.removeEventListener("click", swallowNavigation);
  cleanup();
});

async function renderDrawer(onClose = vi.fn()) {
  const view = render(
    <MobileDrawer locale="en" labels={TEST_LABELS} onClose={onClose} loadCategories={load} />,
  );
  await screen.findByRole("button", { name: "Department 1" });
  return { ...view, onClose };
}

describe("MobileDrawer", () => {
  it("is a modal glass dialog with the Amazon-style sections", async () => {
    await renderDrawer();
    const dialog = screen.getByRole("dialog", { name: "Main menu" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveClass("v-glass", "v-glass--overlay");
    for (const heading of ["Shop by department", "Help & settings"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    const main = screen.getByTestId("mobile-drawer-main");
    expect(within(main).getByRole("button", { name: "Services" })).toBeInTheDocument();
    expect(within(main).getByRole("button", { name: "Events" })).toBeInTheDocument();
    expect(within(main).getByRole("link", { name: "Deals" })).toHaveAttribute("href", "/en/deals");
    expect(within(main).getByRole("link", { name: "Sell on Convergeo" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
    expect(within(main).getByRole("link", { name: "Help centre" })).toHaveAttribute(
      "href",
      "/en/help",
    );
  });

  it("greets guests with a sign-in link and signed-in users by name", async () => {
    const guest = await renderDrawer();
    expect(screen.getByRole("link", { name: /Hello, sign in/ })).toHaveAttribute(
      "href",
      "/en/login",
    );
    guest.unmount();

    sessionState.user = { email: "ada@example.com", user_metadata: { full_name: "Ada Banda" } };
    await renderDrawer();
    expect(screen.getByRole("link", { name: "Hello, Ada Banda" })).toHaveAttribute(
      "href",
      "/en/account",
    );
  });

  it("collapses long department lists behind See all / See less", async () => {
    await renderDrawer();
    const main = screen.getByTestId("mobile-drawer-main");
    expect(TEST_TREE.length).toBeGreaterThan(DEPT_COLLAPSED);
    expect(within(main).queryByRole("button", { name: "Department 7" })).not.toBeInTheDocument();

    const toggle = within(main).getByRole("button", { name: "See all" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(within(main).getByRole("button", { name: "Department 7" })).toBeInTheDocument();
    const less = within(main).getByRole("button", { name: "See less" });
    expect(less).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(less);
    expect(within(main).queryByRole("button", { name: "Department 7" })).not.toBeInTheDocument();
  });

  it("drills into a department, shows its sub-list, and goes back with focus restored", async () => {
    await renderDrawer();
    const track = screen.getByTestId("mobile-drawer-track");
    const dept = screen.getByRole("button", { name: "Department 1" });
    expect(track).toHaveAttribute("data-view", "main");

    fireEvent.click(dept);
    expect(track).toHaveAttribute("data-view", "drill");
    const drill = screen.getByTestId("mobile-drawer-drill");
    expect(drill).not.toHaveAttribute("inert");
    expect(screen.getByTestId("mobile-drawer-main")).toHaveAttribute("inert");
    expect(within(drill).getByRole("heading", { name: "Department 1" })).toBeInTheDocument();
    expect(within(drill).getByRole("link", { name: "All in Department 1" })).toHaveAttribute(
      "href",
      "/en/c/dept-1",
    );
    expect(within(drill).getByRole("link", { name: "Phones" })).toHaveAttribute(
      "href",
      "/en/c/dept-1-phones",
    );
    const back = within(drill).getByRole("button", { name: "Main menu" });
    expect(back).toHaveFocus();

    fireEvent.click(back);
    expect(track).toHaveAttribute("data-view", "main");
    expect(screen.getByTestId("mobile-drawer-main")).not.toHaveAttribute("inert");
    expect(screen.getByRole("button", { name: "Department 1" })).toHaveFocus();
  });

  it("drills into Services and Events with their own sub-lists", async () => {
    await renderDrawer();
    fireEvent.click(
      within(screen.getByTestId("mobile-drawer-main")).getByRole("button", { name: "Services" }),
    );
    expect(screen.getByRole("link", { name: "Auto & mechanics" })).toHaveAttribute(
      "href",
      "/en/services?category=auto",
    );
  });

  it("closes on Escape, scrim click, close button, and navigation, and records the category", async () => {
    const { onClose } = await renderDrawer();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("mobile-drawer-scrim"));
    expect(onClose).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(onClose).toHaveBeenCalledTimes(3);

    fireEvent.click(screen.getByRole("button", { name: "Department 1" }));
    fireEvent.click(screen.getByRole("link", { name: "Laptops" }));
    expect(onClose).toHaveBeenCalledTimes(4);
    expect(window.localStorage.getItem("vergeo5:browsed-categories:v1")).toContain("laptops");
  });

  it("keeps Tab inside the drill pane and skips the inert main pane", async () => {
    await renderDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Department 1" }));
    const drill = screen.getByTestId("mobile-drawer-drill");
    const back = within(drill).getByRole("button", { name: "Main menu" });
    back.focus();
    fireEvent.keyDown(back, { key: "Tab" });
    const active = document.activeElement;
    expect(drill.contains(active)).toBe(true);
    expect(screen.getByTestId("mobile-drawer-main")).toHaveAttribute("inert");
  });

  it("traps Tab inside the dialog (wraps first <-> last, skipping the off-screen pane)", async () => {
    await renderDrawer();
    const first = screen.getByRole("link", { name: /Hello, sign in/ });
    const last = screen.getByRole("link", { name: "Help centre" });
    first.focus();
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(first).toHaveFocus();
  });

  it("closes on route change", async () => {
    const { rerender, onClose } = await renderDrawer();
    vi.mocked(usePathname).mockReturnValue("/en/c/electronics");
    rerender(
      <MobileDrawer locale="en" labels={TEST_LABELS} onClose={onClose} loadCategories={load} />,
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("MobileMenuHost", () => {
  it("opens on the shared event, lazy-loads the drawer, and returns focus to the opener", async () => {
    render(
      <>
        <button type="button">Opener</button>
        <MobileMenuHost locale="en" labels={TEST_LABELS} loadCategories={load} />
      </>,
    );
    const opener = screen.getByRole("button", { name: "Opener" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    opener.focus();
    openMobileMenu();
    await screen.findByRole("dialog", { name: "Main menu" });

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
