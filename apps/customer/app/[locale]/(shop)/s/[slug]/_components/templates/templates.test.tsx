// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { formatK } from "@vergeo/i18n";
import { createTranslator } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../../../packages/i18n/messages/en/catalog.json";
import servicesMessages from "../../../../../../../../../packages/i18n/messages/en/services.json";
import { useSession } from "../../../../../../../lib/customer-session";
import { buildPanelLabels } from "../../_lib/panel-labels";

import { AccommodationLayout } from "./accommodation-layout";
import { AppointmentLayout, groupMenu } from "./appointment-layout";
import { ArchetypeLayout } from "./archetype-layout";
import { bestValueId, groupSchedule, MembershipLayout } from "./membership-layout";
import { parseSpecs, RentalLayout } from "./rental-layout";
import { ServiceRequestPanel } from "./request-panel";
import { ServiceHero } from "./service-hero";

import type { RequestQuoteLabels } from "../../../../_components/pdp/request-quote-button";
import type { ServicePackage } from "../service-packages-model";
import type { T } from "./shared";

vi.mock("../../../../../../../lib/customer-session", () => ({ useSession: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/en/s/svc-1" }));
const createRfq = vi.fn();
vi.mock("../../../../../../../lib/rfq-api", () => ({
  createRfqApiClient: () => ({ createRfq: (...args: unknown[]) => createRfq(...args) }),
  RFQ_DETAILS_MAX_CHARS: 4000,
}));

const translator = createTranslator({
  locale: "en",
  messages: { services: servicesMessages },
  namespace: "services.templates",
});
const t = ((key: string, values?: Record<string, string | number>) =>
  (translator as unknown as (k: string, v?: Record<string, string | number>) => string)(
    key,
    values,
  )) as T;
const quoteLabels = catalogMessages.pdp.requestQuote as RequestQuoteLabels;

function offer(id: string, name: string, price: number | null, attributes = {}): ServicePackage {
  return {
    id,
    name,
    description: null,
    price_ngwee: price,
    delivery_days: 1,
    revisions: null,
    includes: [],
    attributes,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ServiceHero", () => {
  const base = {
    archetype: "accommodation" as const,
    archetypeLabel: "Stays",
    title: "Kafue Lodge",
    area: "Kafue",
    priceLine: "From K800.00",
    responseLine: null,
    badges: null,
  };

  it("shows a vibe banner (never an empty half) when there are no photos", () => {
    render(<ServiceHero {...base} images={[]} />);
    expect(screen.getByTestId("service-hero-banner")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Kafue Lodge");
    expect(screen.getByTestId("service-hero")).toHaveAttribute("data-archetype", "accommodation");
  });

  it("uses a mosaic for three or more photos and one wide photo otherwise", () => {
    const { rerender } = render(<ServiceHero {...base} images={["a", "b", "c", "d"]} />);
    expect(screen.getByTestId("service-hero-mosaic")).toBeInTheDocument();
    rerender(<ServiceHero {...base} images={["a"]} />);
    expect(screen.queryByTestId("service-hero-mosaic")).toBeNull();
    expect(screen.queryByTestId("service-hero-banner")).toBeNull();
  });
});

describe("ArchetypeLayout", () => {
  it("renders nothing for archetypes without a bespoke layout (generic fallback)", () => {
    const { container } = render(
      <ArchetypeLayout archetype="on_site" offers={[]} attrs={{}} t={t} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("AccommodationLayout", () => {
  const rooms = [
    offer("r1", "Garden room", 80_000, {
      room_type: "premium",
      sleeps: 3,
      beds: 2,
      bed_type: "queen",
      breakfast_included: true,
      min_nights: 2,
      units_available: 2,
      amenities: ["Wi-Fi"],
    }),
    offer("r2", "Chalet", 150_000, { stay_kind: "monthly" }),
  ];

  it("renders room cards with capacity, beds and nightly or monthly price", () => {
    render(
      <AccommodationLayout
        offers={rooms}
        attrs={{
          check_in: "14:00",
          check_out: "10:00",
          amenities: ["Pool"],
          availability: "limited",
        }}
        t={t}
      />,
    );
    const room = within(screen.getByTestId("room-r1"));
    expect(room.getByText("Premium")).toBeInTheDocument();
    expect(room.getByText("Sleeps 3 guests")).toBeInTheDocument();
    expect(room.getByText("2 queen beds")).toBeInTheDocument();
    expect(room.getByText("Breakfast included")).toBeInTheDocument();
    expect(room.getByText("Min 2 nights")).toBeInTheDocument();
    expect(room.getByText("Only 2 left")).toBeInTheDocument();
    expect(room.getByTestId("offer-price")).toHaveTextContent(`${formatK(80_000)}/ night`);
    expect(within(screen.getByTestId("room-r2")).getByTestId("offer-price")).toHaveTextContent(
      "/ month",
    );
    expect(screen.getByTestId("accommodation-facts")).toHaveTextContent("14:00");
    expect(screen.getByTestId("accommodation-facts")).toHaveTextContent("Limited availability");
    expect(screen.getByTestId("amenity-grid")).toHaveTextContent("Pool");
  });

  it("explains what to do when no rooms are listed", () => {
    render(<AccommodationLayout offers={[]} attrs={{}} t={t} />);
    expect(screen.getByText(/No options are listed yet/)).toBeInTheDocument();
  });
});

describe("AppointmentLayout", () => {
  const menu = [
    offer("a", "Fade cut", 15_000, { duration_min: 45, group: "Hair", staff: ["Mwila"] }),
    offer("b", "Beard trim", 8_000, { duration_min: 20, group: "Hair", price_is_from: true }),
    offer("c", "Home visit", 30_000, { duration_min: 90, home_visit: true }),
  ];

  it("groups the menu, putting ungrouped items first", () => {
    const groups = groupMenu(menu);
    expect(groups.map((g) => g.group)).toEqual(["", "Hair"]);
    expect(groups[1]?.items.map((i) => i.id)).toEqual(["a", "b"]);
  });

  it("renders durations, from-prices, home visits and the team", () => {
    render(
      <AppointmentLayout
        offers={menu}
        attrs={{ staff: [{ name: "Mwila", role: "Barber" }], walk_ins: true }}
        t={t}
      />,
    );
    expect(within(screen.getByTestId("treatment-a")).getByText("45 min")).toBeInTheDocument();
    expect(within(screen.getByTestId("treatment-c")).getByText("1 h 30 min")).toBeInTheDocument();
    expect(within(screen.getByTestId("treatment-c")).getByText("Home visits")).toBeInTheDocument();
    expect(within(screen.getByTestId("treatment-b")).getByTestId("offer-price")).toHaveTextContent(
      "From",
    );
    expect(screen.getByTestId("staff")).toHaveTextContent("Barber");
    expect(screen.getByTestId("appointment-facts")).toHaveTextContent("Walk-ins");
  });
});

describe("MembershipLayout", () => {
  const passes = [
    offer("day", "Day pass", 5_000, { pass_kind: "day", valid_days: 1, visits_included: 1 }),
    offer("mon", "Monthly", 30_000, {
      pass_kind: "month",
      valid_days: 30,
      classes_included: true,
      guest_passes: 2,
    }),
    offer("ask", "Corporate", null, { pass_kind: "year", valid_days: 365 }),
  ];

  it("picks the best value by cost per valid day, only when two or more compare", () => {
    expect(bestValueId(passes)).toBe("mon");
    expect(bestValueId([passes[0] as ServicePackage])).toBeNull();
  });

  it("groups the schedule by day in order", () => {
    const rows = groupSchedule([
      { day: 3, start: "07:00", title: "Spin", duration_min: 45, capacity: null },
      { day: 1, start: "06:00", title: "Box", duration_min: 60, capacity: 12 },
    ]);
    expect(rows.map((r) => r.day)).toEqual([1, 3]);
  });

  it("renders pass cards, the best-value highlight and the weekly schedule", () => {
    render(
      <MembershipLayout
        offers={passes}
        attrs={{
          class_schedule: [{ day: 1, start: "06:00", title: "Boxing", capacity: 12 }],
          amenities: ["Showers"],
        }}
        t={t}
      />,
    );
    const monthly = within(screen.getByTestId("pass-mon"));
    expect(monthly.getByText("Best value")).toBeInTheDocument();
    expect(monthly.getByText("Classes included")).toBeInTheDocument();
    expect(monthly.getByText("2 guest passes")).toBeInTheDocument();
    expect(monthly.getByText("Unlimited visits")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("pass-day")).getByText("1 visit included"),
    ).toBeInTheDocument();
    expect(within(screen.getByTestId("pass-ask")).getByTestId("offer-price")).toHaveTextContent(
      "Ask for price",
    );
    expect(screen.getByTestId("schedule")).toHaveTextContent("Monday");
    expect(screen.getByTestId("schedule")).toHaveTextContent("Boxing");
    expect(screen.getByTestId("amenity-grid")).toHaveTextContent("Showers");
  });
});

describe("RentalLayout", () => {
  it("parses specs and drops incomplete ones", () => {
    expect(parseSpecs([{ label: "Seats", value: "7" }, { label: "x" }, 3])).toEqual([
      { label: "Seats", value: "7" },
    ]);
  });

  it("renders items with unit price, spec chips and an informational deposit", () => {
    render(
      <RentalLayout
        offers={[
          offer("car", "Toyota Hiace", 120_000, {
            unit: "day",
            deposit_ngwee: 500_000,
            quantity_available: 3,
            specs: [{ label: "Seats", value: "14" }],
            with_operator: true,
            min_period: 2,
          }),
        ]}
        attrs={{ pickup_note: "Kabulonga depot" }}
        t={t}
      />,
    );
    const card = within(screen.getByTestId("rental-car"));
    expect(card.getByTestId("offer-price")).toHaveTextContent(`${formatK(120_000)}/ day`);
    expect(card.getByText("Seats: 14")).toBeInTheDocument();
    expect(card.getByText("With operator")).toBeInTheDocument();
    expect(card.getByText("Min 2 days")).toBeInTheDocument();
    expect(card.getByTestId("rental-deposit")).toHaveTextContent(formatK(500_000));
    expect(card.getByTestId("rental-deposit")).toHaveTextContent("paid to the provider");
    expect(screen.getByTestId("rental-facts")).toHaveTextContent("Kabulonga depot");
  });
});

describe("ServiceRequestPanel", () => {
  const rooms = [offer("r1", "Garden room", 80_000), offer("r2", "Chalet", 150_000)];

  function panel(archetype: "accommodation" | "appointment" | "rental", offers = rooms) {
    return render(
      <ServiceRequestPanel
        locale="en"
        serviceId="svc-1"
        vendorName="Kafue Lodge"
        archetype={archetype}
        offers={offers}
        staffNames={["Mwila"]}
        labels={buildPanelLabels(t, archetype)}
        quoteLabels={quoteLabels}
      />,
    );
  }

  beforeEach(() => {
    vi.mocked(useSession).mockReturnValue({
      session: { access_token: "token" },
      loading: false,
    } as ReturnType<typeof useSession>);
    createRfq.mockResolvedValue({
      thread: { id: "t1" },
      message: { id: "m1" },
      reused_existing_thread: false,
    });
  });

  it("blocks the request until an option and valid dates are chosen, naming the problem", async () => {
    const user = userEvent.setup();
    panel("accommodation");
    await user.click(screen.getByTestId("request-cta-blocked"));
    expect(screen.getByTestId("request-error")).toHaveTextContent("Choose an option first.");
    await user.selectOptions(screen.getByTestId("request-offer"), "r1");
    await user.click(screen.getByTestId("request-cta-blocked"));
    expect(screen.getByTestId("request-error")).toHaveTextContent("Pick a date.");
    expect(createRfq).not.toHaveBeenCalled();
  });

  it("pre-fills the quote request with the offer, dates and guests and sends the package id", async () => {
    const user = userEvent.setup();
    panel("accommodation");
    await user.selectOptions(screen.getByTestId("request-offer"), "r2");
    await user.type(screen.getByTestId("request-start"), "2099-12-05");
    await user.type(screen.getByTestId("request-end"), "2099-12-08");
    await user.clear(screen.getByTestId("request-guests"));
    await user.type(screen.getByTestId("request-guests"), "3");
    await user.click(await screen.findByTestId("request-cta"));

    const details = screen.getByTestId("pdp-request-quote-details") as HTMLTextAreaElement;
    expect(details.value).toContain("Option: Chalet");
    expect(details.value).toContain("Check-in: 2099-12-05");
    expect(details.value).toContain("Check-out: 2099-12-08 (3 nights)");
    expect(details.value).toContain("Guests: 3");

    await user.click(screen.getByTestId("pdp-request-quote-submit"));
    await waitFor(() => expect(createRfq).toHaveBeenCalledTimes(1));
    const payload = createRfq.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.service_id).toBe("svc-1");
    expect(payload.package_id).toBe("r2");
    expect(String(payload.requested_details)).toContain("Check-out: 2099-12-08");
  });

  it("selects an offer when a card's choose button fires the select event", async () => {
    panel("accommodation");
    window.dispatchEvent(new CustomEvent("service-offer-select", { detail: "r1" }));
    await waitFor(() =>
      expect((screen.getByTestId("request-offer") as HTMLSelectElement).value).toBe("r1"),
    );
  });

  it("shows only the stylist field for appointments, and no payment promise", () => {
    panel("appointment");
    expect(screen.getByTestId("request-staff")).toBeInTheDocument();
    expect(screen.queryByTestId("request-end")).toBeNull();
    expect(screen.getByText(/Nothing is reserved or paid/)).toBeInTheDocument();
  });

  it("preselects the only offer", () => {
    panel("rental", [offer("only", "Projector", 10_000)]);
    expect((screen.getByTestId("request-offer") as HTMLSelectElement).value).toBe("only");
  });
});
