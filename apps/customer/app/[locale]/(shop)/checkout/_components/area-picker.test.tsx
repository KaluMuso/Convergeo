// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { AreaPicker, type AreaPickerLabels, type DeliveryArea, filterAreas } from "./area-picker";
import { promiseCopy } from "./step-fulfilment-step";

import type { AddressType } from "../../../../../lib/delivery-estimate";

const AREAS: DeliveryArea[] = [
  { slug: "kabulonga", name: "Kabulonga", aliases: [] },
  { slug: "woodlands", name: "Woodlands", aliases: [] },
  { slug: "woodlands_extension", name: "Woodlands Extension", aliases: ["woodlands ext"] },
  { slug: "chelstone", name: "Chelstone", aliases: ["chelston"] },
  { slug: "ngombe", name: "Ng'ombe", aliases: ["ngombe"] },
];

const labels: AreaPickerLabels = {
  label: "Your area",
  help: "Optional",
  searchPlaceholder: "Search",
  noMatch: "No area matches",
  notListed: "Area not listed?",
  change: "Change",
  selectedTemplate: "Area: {area}",
  unavailable: "List did not load",
  typeLabel: "This address is",
  home: "Home",
  work: "Work",
  workHelp: "Before 16:45 on weekdays",
};

function Harness({ areas }: { areas: DeliveryArea[] | null }) {
  const [slug, setSlug] = useState<string | null>(null);
  const [type, setType] = useState<AddressType>("home");
  return (
    <>
      <AreaPicker
        areas={areas}
        value={slug}
        onChange={setSlug}
        addressType={type}
        onAddressTypeChange={setType}
        labels={labels}
      />
      <output data-testid="state">{`${slug ?? "none"}|${type}`}</output>
    </>
  );
}

afterEach(cleanup);

describe("filterAreas", () => {
  it("matches names and aliases, ignoring case and apostrophes", () => {
    expect(filterAreas(AREAS, "chelston").map((a) => a.slug)).toEqual(["chelstone"]);
    expect(filterAreas(AREAS, "NGOMBE").map((a) => a.slug)).toEqual(["ngombe"]);
    expect(filterAreas(AREAS, "wood").map((a) => a.slug)).toEqual([
      "woodlands",
      "woodlands_extension",
    ]);
    expect(filterAreas(AREAS, "zzz")).toEqual([]);
  });
});

describe("AreaPicker", () => {
  it("searches, picks an area, and can change it", async () => {
    const user = userEvent.setup();
    render(<Harness areas={AREAS} />);
    await user.type(screen.getByPlaceholderText("Search"), "kabu");
    await user.click(screen.getByRole("button", { name: "Kabulonga" }));
    expect(screen.getByText("Area: Kabulonga")).toBeInTheDocument();
    expect(screen.getByTestId("state")).toHaveTextContent("kabulonga|home");
    await user.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.getByTestId("state")).toHaveTextContent("none|home");
  });

  it("offers Home and Work, explaining office hours for Work", async () => {
    const user = userEvent.setup();
    render(<Harness areas={AREAS} />);
    expect(screen.queryByText("Before 16:45 on weekdays")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Work" }));
    expect(screen.getByText("Before 16:45 on weekdays")).toBeInTheDocument();
    expect(screen.getByTestId("state")).toHaveTextContent("none|work");
  });

  it("keeps the landmark route open when nothing matches or the list fails", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness areas={AREAS} />);
    await user.type(screen.getByPlaceholderText("Search"), "zzz");
    expect(screen.getByText("No area matches")).toBeInTheDocument();
    unmount();
    render(<Harness areas={null} />);
    expect(screen.getByText("List did not load")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Home" })).toBeChecked();
  });
});

describe("promiseCopy", () => {
  const guide = {
    deliveryHelp: "",
    pickupHelp: "",
    groupHint: "",
    tipsTitle: "",
    tip1: "",
    tip2: "",
    tip3: "",
    landmarkRequired: "",
    cutoffTitle: "",
    cutoffBefore: "",
    cutoffAfter: "",
    cutoffMadeToOrder: "",
    promiseTodayTemplate: "Delivery today, {start}–{end}",
    promiseTomorrowTemplate: "Delivery tomorrow, {start}–{end}",
    promiseLaterTemplate: "Delivery on {date}, {start}–{end}",
  };
  it("fills the window and day", () => {
    const fmt = (iso: string) => `D:${iso}`;
    expect(
      promiseCopy(
        { day: "today", date: "2026-11-18", windowStart: "17:00", windowEnd: "19:30" },
        guide,
        fmt,
      ),
    ).toBe("Delivery today, 17:00–19:30");
    expect(
      promiseCopy(
        { day: "later", date: "2026-11-23", windowStart: "12:00", windowEnd: "14:30" },
        guide,
        fmt,
      ),
    ).toBe("Delivery on D:2026-11-23, 12:00–14:30");
    expect(
      promiseCopy(
        { day: "today", date: "2026-11-18", windowStart: "17:00", windowEnd: "19:30" },
        undefined,
        fmt,
      ),
    ).toBeNull();
  });
});
