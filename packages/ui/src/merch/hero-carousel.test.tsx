// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HeroCarousel } from "./hero-carousel";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const labels = {
  previous: "Previous slide",
  next: "Next slide",
  slideOf: (current: number, total: number) => `Slide ${current} of ${total}`,
  ariaLabel: "Homepage hero carousel",
};

const slides = [
  {
    key: "one",
    title: "First slide",
    media: <div data-testid="slide-media-0">Media 0</div>,
  },
  {
    key: "two",
    title: "Second slide",
    media: <div data-testid="slide-media-1">Media 1</div>,
  },
  {
    key: "three",
    title: "Third slide",
    media: <div data-testid="slide-media-2">Media 2</div>,
  },
];

function mockMatchMedia(matches: Record<string, boolean>) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matches[query] ?? false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

describe("HeroCarousel", () => {
  beforeEach(() => {
    mockMatchMedia({});
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });

  it("exposes carousel region semantics and per-slide labels", () => {
    render(<HeroCarousel slides={slides} labels={labels} />);

    expect(screen.getByTestId("hero-carousel")).toHaveAttribute("role", "region");
    expect(screen.getByTestId("hero-carousel")).toHaveAttribute("aria-roledescription", "carousel");
    expect(screen.getByTestId("hero-carousel-slide-0")).toHaveAttribute(
      "aria-label",
      "Slide 1 of 3",
    );
    expect(screen.getByTestId("hero-carousel-slide-2")).toHaveAttribute(
      "aria-label",
      "Slide 3 of 3",
    );
    expect(screen.getByTestId("hero-carousel-fade")).toBeInTheDocument();
  });

  it("loops to the next slide via controls and announces manual changes", () => {
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(<HeroCarousel slides={slides} labels={labels} />);

    fireEvent.click(screen.getByTestId("hero-carousel-next"));
    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByTestId("hero-carousel-live")).toHaveTextContent("Slide 2 of 3");

    fireEvent.click(screen.getByTestId("hero-carousel-dot-2"));
    expect(screen.getByTestId("hero-carousel-live")).toHaveTextContent("Slide 3 of 3");
  });

  it("supports arrow-key navigation", () => {
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(<HeroCarousel slides={slides} labels={labels} />);

    fireEvent.keyDown(screen.getByTestId("hero-carousel"), { key: "ArrowRight" });
    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByTestId("hero-carousel-live")).toHaveTextContent("Slide 2 of 3");
  });

  it("auto-advances on an interval unless reduced motion is preferred", () => {
    vi.useFakeTimers();
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(<HeroCarousel slides={slides} labels={labels} autoAdvanceMs={1000} />);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("hero-carousel-live")).toHaveTextContent("");
  });

  it("does not auto-advance when prefers-reduced-motion is set", () => {
    vi.useFakeTimers();
    mockMatchMedia({ "(prefers-reduced-motion: reduce)": true });
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(<HeroCarousel slides={slides} labels={labels} autoAdvanceMs={1000} />);

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("pauses auto-advance while hovered", () => {
    vi.useFakeTimers();
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    const { getByTestId } = render(
      <HeroCarousel slides={slides} labels={labels} autoAdvanceMs={1000} />,
    );
    fireEvent.mouseEnter(getByTestId("hero-carousel"));

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("renders prev/next controls with at least 44px hit targets", () => {
    render(<HeroCarousel slides={slides} labels={labels} />);

    expect(screen.getByTestId("hero-carousel-prev")).toHaveStyle({ minHeight: "44px" });
    expect(screen.getByTestId("hero-carousel-next")).toHaveStyle({ minWidth: "44px" });
  });
});
