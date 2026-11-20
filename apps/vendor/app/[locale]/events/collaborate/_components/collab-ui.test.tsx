import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import events from "../../../../../../../packages/i18n/messages/en/events.json";
import vendor from "../../../../../../../packages/i18n/messages/en/vendor.json";
import { OrganiserGate } from "../../_components/organiser-gate";
import { type CollabRequest } from "../_lib/collab-client";

import { CollabDetail } from "./collab-detail";
import { CollabForm } from "./collab-form";
import { CollabList } from "./collab-list";

const client = {
  getStatus: vi.fn(),
  listRequests: vi.fn(),
  getRequest: vi.fn(),
  listOrganisers: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  submit: vi.fn(),
  approve: vi.fn(),
  decline: vi.fn(),
  requestChanges: vi.fn(),
  publish: vi.fn(),
};

vi.mock("../_lib/collab-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../_lib/collab-client")>()),
  createCollabClient: () => client,
}));
vi.mock("../../_lib/events-client", () => ({
  createEventsClient: () => ({
    listCategories: () =>
      Promise.resolve([
        { slug: "music", parent_slug: null, label_key: "categories.music" },
      ]),
  }),
}));
vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "t" },
    user: { id: "u" },
    loading: false,
  }),
}));
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/en/events/collaborate",
}));

function ui(node: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ vendor, events }}>
      {node}
    </NextIntlClientProvider>,
  );
}

function request(over: Partial<CollabRequest> = {}): CollabRequest {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    status: "submitted",
    my_role: "organiser",
    proposer: { vendor_id: "p", display_name: "Proposer Shop", slug: "prop" },
    organiser: { vendor_id: "o", display_name: "Big Events", slug: "org" },
    event_draft: { title: "Collab night", category: "music" },
    checklist: {
      venue: { name: "Hall", landmark: "Mall", lat: -15.4, lng: 28.3 },
      schedule: {
        starts_at: "2031-01-01T18:00:00Z",
        ends_at: "2031-01-01T22:00:00Z",
      },
      capacity: { capacity: 200 },
      equipment: {
        sound: "ready",
        stage: "needed",
        power: "ready",
        seating: "ready",
        security: "ready",
      },
      permits: { status: "pending", note: null },
      tiers: [{ name: "General", price_ngwee: 5000, qty_cap: 150 }],
    },
    readiness_pct: 82,
    revenue_share_bps: 2500,
    organiser_note: null,
    event_id: null,
    submitted_at: null,
    decided_at: null,
    published_at: null,
    created_at: "2026-11-15T10:00:00Z",
    updated_at: "2026-11-15T10:00:00Z",
    audit: [],
    ...over,
  };
}

beforeEach(() => {
  for (const fn of Object.values(client)) fn.mockReset();
  client.getStatus.mockResolvedValue({
    enabled: true,
    can_organise: true,
    accepts_requests: true,
  });
  client.listOrganisers.mockResolvedValue({
    items: [
      { vendor_id: "o", slug: "org", display_name: "Big Events", blurb: null },
    ],
  });
});
afterEach(cleanup);

it("gate keeps the disabled coming-soon stub while the flag is off", () => {
  ui(<OrganiserGate locale="en" />);
  expect(
    (screen.getByTestId("organiser-gate-collaborate") as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(screen.getByText(/Coming soon/)).toBeTruthy();
});

it("gate links to the real flow when the flag is on", () => {
  ui(<OrganiserGate locale="en" collaborationEnabled />);
  const link = screen.getByTestId("organiser-gate-collaborate");
  expect(link.getAttribute("href")).toBe("/en/events/collaborate");
  expect(screen.queryByText(/Coming soon/)).toBeNull();
});

it("organiser inbox lists incoming requests with readiness", async () => {
  client.listRequests.mockResolvedValue({ items: [request()] });
  ui(<CollabList locale="en" role="organiser" />);
  expect(await screen.findByText("Collab night")).toBeTruthy();
  expect(screen.getByText("From Proposer Shop")).toBeTruthy();
  expect(screen.getByTestId("readiness-pct").textContent).toBe("82% ready");
  expect(client.listRequests).toHaveBeenCalledWith("organiser");
});

it("list shows nothing but a notice when the flag is off", async () => {
  client.getStatus.mockResolvedValue({
    enabled: false,
    can_organise: false,
    accepts_requests: false,
  });
  ui(<CollabList locale="en" role="proposer" />);
  expect(await screen.findByTestId("collab-disabled")).toBeTruthy();
  expect(client.listRequests).not.toHaveBeenCalled();
});

it("organiser can approve a submitted request; decline needs a reason", async () => {
  client.getRequest.mockResolvedValue(request());
  client.approve.mockResolvedValue(request({ status: "approved" }));
  client.decline.mockResolvedValue(
    request({ status: "declined", organiser_note: "No dates" }),
  );
  ui(
    <CollabDetail
      locale="en"
      requestId="11111111-1111-1111-1111-111111111111"
    />,
  );
  fireEvent.click(await screen.findByTestId("collab-approve"));
  await waitFor(() => expect(client.approve).toHaveBeenCalledTimes(1));
  expect(await screen.findByTestId("collab-publish")).toBeTruthy();
  expect(screen.queryByTestId("collab-approve")).toBeNull();
});

it("decline is disabled until a reason is typed", async () => {
  client.getRequest.mockResolvedValue(request());
  client.decline.mockResolvedValue(
    request({ status: "declined", organiser_note: "No dates" }),
  );
  ui(<CollabDetail locale="en" requestId="x" />);
  fireEvent.click(await screen.findByTestId("collab-decline"));
  const confirm = screen.getByTestId(
    "collab-confirm-reason",
  ) as HTMLButtonElement;
  expect(confirm.disabled).toBe(true);
  fireEvent.change(screen.getByTestId("collab-reason"), {
    target: { value: "No dates free" },
  });
  expect(confirm.disabled).toBe(false);
  fireEvent.click(confirm);
  await waitFor(() =>
    expect(client.decline).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      "No dates free",
    ),
  );
});

it("proposer sees no organiser actions on a submitted request", async () => {
  client.getRequest.mockResolvedValue(request({ my_role: "proposer" }));
  ui(<CollabDetail locale="en" requestId="x" />);
  expect(await screen.findByTestId("collab-detail")).toBeTruthy();
  expect(screen.queryByTestId("collab-approve")).toBeNull();
  expect(screen.queryByTestId("collab-publish")).toBeNull();
  expect(screen.getByText("Waiting for the organiser to decide.")).toBeTruthy();
});

it("surfaces an invalid-transition error from the API", async () => {
  client.getRequest.mockResolvedValue(request());
  client.approve.mockRejectedValue(
    new ApiError("invalid_transition", "x", { status: 409 }),
  );
  ui(<CollabDetail locale="en" requestId="x" />);
  fireEvent.click(await screen.findByTestId("collab-approve"));
  expect((await screen.findByTestId("collab-error")).textContent).toMatch(
    /already moved on/,
  );
});

it("form shows a live readiness percentage and blocks an incomplete submit", async () => {
  ui(<CollabForm locale="en" />);
  expect(screen.getByTestId("readiness-pct").textContent).toBe("0% ready");
  fireEvent.change(screen.getByTestId("collab-venue-name"), {
    target: { value: "Hall" },
  });
  fireEvent.change(screen.getByTestId("collab-capacity"), {
    target: { value: "200" },
  });
  await waitFor(() =>
    expect(screen.getByTestId("readiness-pct").textContent).toBe("9% ready"),
  );
  fireEvent.change(screen.getByTestId("collab-share"), {
    target: { value: "25" },
  });
  await waitFor(() =>
    expect(screen.getByTestId("readiness-pct").textContent).toBe("18% ready"),
  );
  expect(screen.getByTestId("collab-share-bps").textContent).toBe(
    "Co-host 25% · Organiser 75%",
  );

  fireEvent.click(await screen.findByTestId("collab-organiser-o"));
  fireEvent.click(screen.getByTestId("collab-submit"));
  expect(await screen.findByTestId("collab-field-errors")).toBeTruthy();
  expect(client.createRequest).not.toHaveBeenCalled();
});

it("form saves a draft with the share as integer basis points", async () => {
  client.createRequest.mockResolvedValue(
    request({ id: "new-id", status: "draft", my_role: "proposer" }),
  );
  ui(<CollabForm locale="en" />);
  fireEvent.click(await screen.findByTestId("collab-organiser-o"));
  fireEvent.change(screen.getByTestId("collab-share"), {
    target: { value: "12.5" },
  });
  fireEvent.click(screen.getByTestId("collab-save"));
  await waitFor(() => expect(client.createRequest).toHaveBeenCalledTimes(1));
  const [organiserId, payload] = client.createRequest.mock.calls[0] as [
    string,
    { revenue_share_bps: number },
  ];
  expect(organiserId).toBe("o");
  expect(payload.revenue_share_bps).toBe(1250);
  await waitFor(() =>
    expect(replace).toHaveBeenCalledWith("/en/events/collaborate/new-id"),
  );
});
