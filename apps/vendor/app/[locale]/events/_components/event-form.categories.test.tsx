import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EventForm } from "./event-form";

const { listCategories } = vi.hoisted(() => ({ listCategories: vi.fn() }));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({ session: { access_token: "t", user: { id: "v" } }, loading: false }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("../_lib/events-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../_lib/events-client")>()),
  createEventsClient: () => ({ listCategories }),
}));
vi.mock("./image-picker", () => ({ EventImagePicker: () => null }));
vi.mock("./event-tool-links", () => ({ EventToolLinks: () => null }));
vi.mock("./instance-editor", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./instance-editor")>()),
  InstanceEditor: () => null,
}));

// Reproduces the production failure mode: `useTranslations` handing back a NEW
// function identity on every render (as it does when a namespace is missing).
// The category fetch must not be keyed on that identity or it restarts on every
// render and "Loading categories" never clears.
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
    { slug: "workshops", parent_slug: null, label_key: "events.categories.workshops" },
    { slug: "music", parent_slug: null, label_key: "events.categories.music" },
  ]);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("EventForm category loading", () => {
  it("finishes loading categories once, even when translators change identity per render", async () => {
    render(<EventForm locale="en" mode="create" />);
    await waitFor(() =>
      expect(screen.queryByText("loading", { exact: false })).not.toBeInTheDocument(),
    );
    expect(listCategories).toHaveBeenCalledTimes(1);
    // The default category resolves to a node, so no "unavailable" alert remains.
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "workshops" })).toBeInTheDocument();
  });

  it("does not flash the unavailable alert while categories are still loading", () => {
    listCategories.mockReturnValue(new Promise(() => undefined));
    render(<EventForm locale="en" mode="create" />);
    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(screen.queryByText("unavailable")).not.toBeInTheDocument();
  });
});
