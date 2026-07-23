import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NearMeToggle } from "./near-me-toggle";

const push = vi.fn();
let currentParams = new URLSearchParams("q=phone");

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => currentParams,
}));

const labels = {
  enable: "Near me",
  active: "Nearest first",
  locating: "Locating…",
  denied: "Location blocked",
  unsupported: "Location unavailable",
  clear: "Show all",
  hint: "Sort by closeness",
};

afterEach(() => {
  cleanup();
  push.mockReset();
  vi.unstubAllGlobals();
  currentParams = new URLSearchParams("q=phone");
});

describe("NearMeToggle", () => {
  it("requests geolocation and pushes coarse (2dp) lat/lng on enable", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({
        coords: { latitude: -15.416789, longitude: 28.283333 },
      } as GeolocationPosition),
    );
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });

    render(<NearMeToggle locale="en" labels={labels} />);
    await userEvent.click(screen.getByTestId("near-me-toggle"));

    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledTimes(1);
    const url = push.mock.calls[0]?.[0] as string;
    expect(url).toContain("lat=-15.42"); // rounded from -15.416789
    expect(url).toContain("lng=28.28"); // rounded from 28.283333
    expect(url).not.toContain("page="); // proximity change resets pagination
  });

  it("clears lat/lng when already active", async () => {
    currentParams = new URLSearchParams("q=phone&lat=-15.42&lng=28.28&page=2");

    render(<NearMeToggle locale="en" labels={labels} />);
    const button = screen.getByTestId("near-me-toggle");
    expect(button).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(button);
    const url = push.mock.calls[0]?.[0] as string;
    expect(url).not.toContain("lat=");
    expect(url).not.toContain("lng=");
  });

  it("shows an unsupported state and does not navigate without geolocation", async () => {
    vi.stubGlobal("navigator", {});

    render(<NearMeToggle locale="en" labels={labels} />);
    await userEvent.click(screen.getByTestId("near-me-toggle"));

    expect(screen.getByText("Location unavailable")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
