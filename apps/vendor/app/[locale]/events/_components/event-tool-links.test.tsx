import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const listEvents = vi.fn();

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "token" }, loading: false }),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));
vi.mock("../_lib/events-client", () => ({
  createEventsClient: () => ({ listEvents }),
}));
vi.mock("../collaborate/_lib/collab-client", () => ({
  createCollabClient: () => ({ getStatus: () => Promise.resolve({ enabled: false }) }),
}));

import { EventToolLinks } from "./event-tool-links";
import { EventsManageList } from "./events-manage-list";

afterEach(() => {
  cleanup();
  listEvents.mockReset();
});

const EXPECTED = [
  ["events.list.ticketsCta", "tickets"],
  ["events.list.scanCta", "scan"],
  ["events.list.salesCta", "dashboard"],
  ["events.list.rosterCta", "roster"],
] as const;

describe("EventToolLinks", () => {
  it("links tickets, door scan, sales and roster for the event", () => {
    render(<EventToolLinks locale="en" eventId="evt-1" t={(key) => key} />);
    for (const [label, path] of EXPECTED) {
      expect(screen.getByText(label).closest("a")?.getAttribute("href")).toBe(
        `/en/events/evt-1/${path}`,
      );
    }
  });
});

describe("EventsManageList tool links", () => {
  it("shows the organiser tool links beside the Edit CTA", async () => {
    listEvents.mockResolvedValue({
      items: [
        {
          id: "evt-9",
          title: "Gig",
          venue: null,
          category: null,
          status: "published",
          tickets_sold: 0,
        },
      ],
    });
    render(<EventsManageList locale="bem" />);
    const edit = await screen.findByText("events.list.editCta");
    expect(edit.closest("a")?.getAttribute("href")).toBe("/bem/events/evt-9/edit");
    for (const [label, path] of EXPECTED) {
      expect(screen.getByText(label).closest("a")?.getAttribute("href")).toBe(
        `/bem/events/evt-9/${path}`,
      );
    }
  });
});
