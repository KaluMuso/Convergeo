// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BROWSED_CATEGORIES_KEY } from "./browsed-categories";
import { MegaMenuLauncher } from "./mega-menu-launcher";
import MegaPanel from "./mega-panel";
import { TEST_LABELS, TEST_TREE } from "./test-fixtures";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/en") }));

const load = () => Promise.resolve(TEST_TREE);

const swallowNavigation = (event: Event) => event.preventDefault();

beforeEach(() => {
  document.addEventListener("click", swallowNavigation);
  vi.useRealTimers();
  window.localStorage.clear();
  vi.mocked(usePathname).mockReturnValue("/en");
});

afterEach(() => {
  document.removeEventListener("click", swallowNavigation);
  cleanup();
  vi.useRealTimers();
});

async function renderPanel(onClose = vi.fn(), hoverDelayMs = 150, heading = "Department 1") {
  const view = render(
    <MegaPanel
      locale="en"
      labels={TEST_LABELS}
      onClose={onClose}
      loadCategories={load}
      hoverDelayMs={hoverDelayMs}
    />,
  );
  await screen.findByRole("heading", { name: heading });
  return { ...view, onClose };
}

describe("MegaPanel", () => {
  it("shows the first department's sub-categories as tiles plus View all and Browse featured", async () => {
    await renderPanel();
    const pane = screen.getByRole("region", { name: "Department 1" });
    expect(pane).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all in Department 1" })).toHaveAttribute(
      "href",
      "/en/c/dept-1",
    );
    expect(screen.getByRole("link", { name: "Phones" })).toHaveAttribute(
      "href",
      "/en/c/dept-1-phones",
    );
    expect(screen.getByRole("link", { name: "Browse featured" })).toHaveAttribute(
      "href",
      "/en/search",
    );
  });

  it("covers products, services and events groups", async () => {
    await renderPanel();
    expect(screen.getByText("Products")).toBeInTheDocument();
    const services = screen.getByRole("button", { name: "Services" });
    const events = screen.getByRole("button", { name: "Events" });
    fireEvent.click(services);
    expect(screen.getByRole("link", { name: "Beauty" })).toHaveAttribute(
      "href",
      "/en/services?category=beauty",
    );
    fireEvent.click(events);
    expect(screen.getByRole("link", { name: "Workshops & education" })).toHaveAttribute(
      "href",
      "/en/events?category=workshops",
    );
  });

  it("switches the pane only after the hover-intent delay, and not for a fly-by", async () => {
    await renderPanel();
    vi.useFakeTimers();
    const second = screen.getByRole("button", { name: "Department 2" });
    const third = screen.getByRole("button", { name: "Department 3" });

    // Fly-by: enter + leave before the delay never switches.
    fireEvent.pointerEnter(second, { pointerType: "mouse" });
    act(() => {
      vi.advanceTimersByTime(100);
    });
    fireEvent.pointerLeave(second);
    fireEvent.pointerEnter(third, { pointerType: "mouse" });
    expect(screen.getByRole("region", { name: "Department 1" })).toBeInTheDocument();

    // Dwell on the third entry: only it activates, after the delay.
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.getByRole("region", { name: "Department 1" })).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(60);
    });
    expect(screen.getByRole("region", { name: "Department 3" })).toBeInTheDocument();
    expect(third).toHaveAttribute("aria-current", "true");
  });

  it("switches immediately on focus and on click", async () => {
    await renderPanel();
    fireEvent.focus(screen.getByRole("button", { name: "Department 2" }));
    expect(screen.getByRole("region", { name: "Department 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Department 4" }));
    expect(screen.getByRole("region", { name: "Department 4" })).toBeInTheDocument();
  });

  it("walks the rail with arrow keys, Home/End, and moves into the pane with ArrowRight", async () => {
    await renderPanel();
    const first = screen.getByRole("button", { name: "Department 1" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(screen.getByRole("button", { name: "Department 2" })).toHaveFocus();
    expect(screen.getByRole("region", { name: "Department 2" })).toBeInTheDocument();

    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: "End" });
    expect(screen.getByRole("button", { name: "Events" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("link", { name: "View all in Department 1" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(first).toHaveFocus();
  });

  it("closes on Escape, scrim click, and route change", async () => {
    const { onClose, rerender } = await renderPanel();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("mega-panel-scrim"));
    expect(onClose).toHaveBeenCalledTimes(2);

    vi.mocked(usePathname).mockReturnValue("/en/c/electronics");
    rerender(
      <MegaPanel locale="en" labels={TEST_LABELS} onClose={onClose} loadCategories={load} />,
    );
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("uses the glass overlay surface", async () => {
    await renderPanel();
    expect(screen.getByRole("dialog", { name: "All categories" })).toHaveClass(
      "v-glass",
      "v-glass--overlay",
    );
  });

  it("offers 'Categories for you' from recently browsed categories and records new clicks", async () => {
    window.localStorage.setItem(
      BROWSED_CATEGORIES_KEY,
      JSON.stringify([{ slug: "chairs", label: "Chairs", href: "/en/c/chairs" }]),
    );
    const { onClose } = await renderPanel(vi.fn(), 150, "Categories for you");
    const forYou = screen.getByRole("button", { name: "Categories for you" });
    fireEvent.click(forYou);
    expect(screen.getByRole("link", { name: "Chairs" })).toHaveAttribute("href", "/en/c/chairs");

    fireEvent.click(screen.getByRole("button", { name: "Department 1" }));
    fireEvent.click(screen.getByRole("link", { name: "Phones" }));
    expect(onClose).toHaveBeenCalled();
    const stored = JSON.parse(window.localStorage.getItem(BROWSED_CATEGORIES_KEY)!);
    expect(stored[0]).toMatchObject({ slug: "dept-1-phones", href: "/en/c/dept-1-phones" });
    expect(stored).toHaveLength(2);
  });

  it("omits 'Categories for you' when nothing was browsed", async () => {
    await renderPanel();
    expect(screen.queryByRole("button", { name: "Categories for you" })).not.toBeInTheDocument();
  });
});

describe("MegaMenuLauncher", () => {
  it("lazy-loads the panel on first open, toggles, and restores focus on Escape", async () => {
    render(<MegaMenuLauncher locale="en" labels={TEST_LABELS} loadCategories={load} />);
    const trigger = screen.getByRole("button", { name: "All Categories" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await screen.findByRole("dialog", { name: "All categories" });

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
