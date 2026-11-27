import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventForm } from "./event-form";

const { listCategories, createEvent, updateEvent } = vi.hoisted(() => ({
  listCategories: vi.fn(),
  createEvent: vi.fn(),
  updateEvent: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "t", user: { id: "v" } },
    loading: false,
  }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("../_lib/events-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../_lib/events-client")>()),
  createEventsClient: () => ({ listCategories, createEvent, updateEvent }),
}));
vi.mock("./image-picker", () => ({ EventImagePicker: () => null }));
vi.mock("./event-tool-links", () => ({ EventToolLinks: () => null }));
vi.mock("./instance-editor", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./instance-editor")>()),
  InstanceEditor: () => null,
  validateInstanceDrafts: () => null,
  draftToPayload: () => [],
}));
vi.mock("next-intl", () => {
  const make = () => {
    const t = (key: string) => key;
    t.has = () => false;
    return t;
  };
  return { useTranslations: () => make() };
});

beforeEach(() => {
  listCategories.mockResolvedValue([
    {
      slug: "workshops",
      parent_slug: null,
      label_key: "events.categories.workshops",
    },
    {
      slug: "church",
      parent_slug: null,
      label_key: "events.categories.church",
    },
  ]);
  createEvent.mockResolvedValue({ event: { id: "e1" } });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function ready() {
  render(<EventForm locale="en" mode="create" />);
  await waitFor(() => expect(screen.queryByText("loading")).not.toBeInTheDocument());
  fireEvent.change(screen.getByLabelText(/events\.form\.title/), {
    target: { value: "Night" },
  });
}

describe("EventForm page style", () => {
  it("defaults to automatic and shows generic fields for a plain category", async () => {
    await ready();
    expect(screen.getByTestId("archetype-select")).toHaveValue("auto");
    expect(screen.getByTestId("archetype-fields")).toHaveAttribute("data-archetype", "generic");
  });

  it("switches the field set when the organiser overrides the style", async () => {
    await ready();
    fireEvent.change(screen.getByTestId("archetype-select"), {
      target: { value: "concert" },
    });
    expect(screen.getByTestId("archetype-fields")).toHaveAttribute("data-archetype", "concert");
    expect(screen.getByText("events.archetype.add.lineup")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("archetype-select"), {
      target: { value: "restaurant" },
    });
    expect(screen.getByText("events.archetype.add.menu_sections")).toBeInTheDocument();
    expect(screen.queryByText("events.archetype.add.lineup")).toBeNull();
  });

  it("sends the override and only the chosen archetype's details on save", async () => {
    await ready();
    fireEvent.change(screen.getByTestId("archetype-select"), {
      target: { value: "concert" },
    });
    fireEvent.click(screen.getByText("events.archetype.add.lineup"));
    fireEvent.change(
      screen.getAllByLabelText(/archetype\.fields\.lineup\.name/)[0] as HTMLElement,
      {
        target: { value: "DJ Zed" },
      },
    );
    fireEvent.click(screen.getByText("events.form.save"));
    await waitFor(() => expect(createEvent).toHaveBeenCalledTimes(1));
    const payload = createEvent.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.archetype).toBe("concert");
    expect(payload.archetype_details).toEqual({ lineup: [{ name: "DJ Zed" }] });
  });

  it("sends a null override (derive from category) and empty details by default", async () => {
    await ready();
    fireEvent.click(screen.getByText("events.form.save"));
    await waitFor(() => expect(createEvent).toHaveBeenCalledTimes(1));
    const payload = createEvent.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload.archetype).toBeNull();
    expect(payload.archetype_details).toEqual({});
  });

  it("blocks save with a localized error when details are invalid", async () => {
    await ready();
    fireEvent.change(screen.getByTestId("archetype-select"), {
      target: { value: "religious" },
    });
    fireEvent.change(screen.getByLabelText(/archetype\.fields\.livestream_url/), {
      target: { value: "http://insecure.example" },
    });
    fireEvent.click(screen.getByText("events.form.save"));
    expect(await screen.findByText("events.archetype.errors.invalidUrl")).toBeInTheDocument();
    expect(createEvent).not.toHaveBeenCalled();
  });
});
