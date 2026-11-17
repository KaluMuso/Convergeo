import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  OtherBranches,
  type OtherBranch,
  type OtherBranchesLabels,
} from "./other-branches";

const labels: OtherBranchesLabels = {
  heading: "Other branches",
  aria: "Other branches of Mwila",
  partOf: "Part of Mwila",
  openNow: "Open now",
  closedNow: "Closed now",
  hours: "Opening hours",
  hoursLine: (day, hours) => `${day}: ${hours}`,
  phone: "Phone:",
  map: "Map",
  visit: (name) => `Visit ${name}`,
  kmAway: "{km} km away",
  metresAway: "{m} m away",
};

const kabwata: OtherBranch = {
  slug: "mwila-kabwata",
  display_name: "Mwila Kabwata",
  landmark: "Opposite Kabwata market",
  address: "Plot 1",
  lat: -15.44,
  lng: 28.3,
  hours: { mon: "08:00-18:00" },
  open_now: true,
  phone: "260971234567",
  map_url: "https://www.google.com/maps/search/?api=1&query=-15.44,28.3",
};

beforeEach(() => window.sessionStorage.clear());
afterEach(() => cleanup());

describe("OtherBranches", () => {
  it("renders a card per branch with landmark, hours, phone as text, map and shop links", () => {
    render(
      <OtherBranches
        locale="en"
        labels={labels}
        branches={[
          kabwata,
          {
            slug: "matero",
            display_name: "Matero",
            landmark: null,
            open_now: false,
          },
        ]}
      />,
    );
    const cards = screen.getAllByTestId("branch-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]?.textContent).toContain("Opposite Kabwata market · Plot 1");
    expect(cards[0]?.textContent).toContain("Open now");
    expect(cards[0]?.textContent).toContain("mon: 08:00-18:00");
    expect(screen.getByTestId("branch-phone").tagName).toBe("SPAN"); // text, not a tel: link
    const visit = screen.getByRole("link", { name: "Visit Mwila Kabwata" });
    expect(visit.getAttribute("href")).toBe("/en/v/mwila-kabwata");
    expect(screen.getByRole("link", { name: "Map" }).getAttribute("href")).toBe(
      kabwata.map_url,
    );
    expect(cards[1]?.textContent).toContain("Closed now");
    expect(cards[1]?.querySelector("a[target]")).toBeNull(); // no map without a link
  });

  it("renders nothing without branches", () => {
    const { container } = render(
      <OtherBranches locale="en" labels={labels} branches={[]} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("shows distance only when the customer location is known", async () => {
    const { unmount } = render(
      <OtherBranches locale="en" labels={labels} branches={[kabwata]} />,
    );
    expect(screen.queryByTestId("branch-distance")).toBeNull();
    unmount();
    window.sessionStorage.setItem("cv_near", "-15.42,28.28");
    render(<OtherBranches locale="en" labels={labels} branches={[kabwata]} />);
    expect((await screen.findByTestId("branch-distance")).textContent).toMatch(
      /^3\.\d km away$/,
    );
  });
});
