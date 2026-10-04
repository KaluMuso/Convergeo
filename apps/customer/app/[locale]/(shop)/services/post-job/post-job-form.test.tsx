import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../../../../../packages/i18n/messages/en/services.json";

import { PostJobForm } from "./post-job-form";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  session: null as { access_token: string } | null,
  loading: false,
}));
vi.mock("../../../../../lib/customer-session", () => ({
  useSession: () => ({ session: mocks.session, loading: mocks.loading }),
}));
vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request: mocks.request }),
}));

const key = "vergeo5:post-job-draft";
const draft = {
  category: "cleaning",
  description: "Clean the kitchen please",
  service_area: "Lusaka, Woodlands",
  preferred_date: "2026-10-20",
  budget_band: "500_2000",
};
const fields = () => ({
  description: screen.getByLabelText(messages.postJob.description.label),
  area: screen.getByLabelText(messages.postJob.serviceArea.label),
  category: screen.getByLabelText(messages.postJob.category.label),
  date: screen.getByLabelText(messages.postJob.preferredDate.label),
  budget: screen.getByLabelText(messages.postJob.budgetBand.label),
});
function ui(initialCategory?: string) {
  return (
    <NextIntlClientProvider locale="en" messages={{ services: { postJob: messages.postJob } }}>
      <PostJobForm locale="en" initialCategory={initialCategory} />
    </NextIntlClientProvider>
  );
}
function fill() {
  fireEvent.change(fields().description, { target: { value: draft.description } });
  fireEvent.change(fields().area, { target: { value: draft.service_area } });
}
function submit(container: HTMLElement) {
  fireEvent.submit(container.querySelector("form")!);
}
function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  mocks.request.mockReturnValueOnce(promise);
  return { resolve, reject };
}

beforeEach(() => {
  mocks.session = null;
  mocks.loading = false;
  mocks.request.mockReset();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("post-job draft resilience", () => {
  it("keeps the form usable when access to localStorage is denied", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("Denied", "SecurityError");
    });
    const { container } = render(ui());
    fill();
    submit(container);
    expect(fields().description).toHaveValue(draft.description);
    expect(screen.queryByText(messages.postJob.draftSaved)).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(messages.postJob.authRequired);
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it.each(["SecurityError", "QuotaExceededError"])(
    "recovers from %s without claiming unsaved edits are saved",
    (name) => {
      render(ui());
      expect(screen.getByText(messages.postJob.draftSaved)).toBeInTheDocument();
      const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("Cannot save", name);
      });
      fill();
      expect(fields().description).toHaveValue(draft.description);
      expect(screen.queryByText(messages.postJob.draftSaved)).not.toBeInTheDocument();
      write.mockRestore();
      fireEvent.change(fields().area, { target: { value: "Kitwe" } });
      expect(screen.getByText(messages.postJob.draftSaved)).toBeInTheDocument();
      expect(JSON.parse(localStorage.getItem(key)!)).toMatchObject({
        description: draft.description,
        service_area: "Kitwe",
      });
      expect(mocks.request).not.toHaveBeenCalled();
    },
  );

  it.each([
    "{broken",
    "null",
    "42",
    '"text"',
    "[]",
    '{"description":{},"service_area":12,"category":"unknown","budget_band":"invalid","preferred_date":[]}',
  ])("handles malformed or wrong-shaped draft %s", (raw) => {
    localStorage.setItem(key, raw);
    render(ui());
    expect(fields().description).toHaveValue("");
    expect(fields().area).toHaveValue("");
    expect(fields().category).toHaveValue("home_services");
    expect(fields().budget).toHaveValue("flexible");
    expect(fields().date).toHaveValue("");
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("preserves valid fields of a partially invalid draft", () => {
    localStorage.setItem(
      key,
      JSON.stringify({ ...draft, category: {}, budget_band: [], preferred_date: "not-a-date" }),
    );
    render(ui());
    expect(fields().description).toHaveValue(draft.description);
    expect(fields().area).toHaveValue(draft.service_area);
    expect(fields().category).toHaveValue("home_services");
    expect(fields().budget).toHaveValue("flexible");
    expect(fields().date).toHaveValue("");
  });

  it.each([
    [undefined, "cleaning"],
    ["food-catering", "food_catering"],
    ["tech_services", "tech_services"],
    ["unknown", "cleaning"],
  ])("restores a valid draft with initial category %s taking precedence", (initial, category) => {
    localStorage.setItem(key, JSON.stringify(draft));
    render(ui(initial));
    expect(fields().category).toHaveValue(category);
    expect(fields().description).toHaveValue(draft.description);
    expect(fields().area).toHaveValue(draft.service_area);
    expect(fields().date).toHaveValue(draft.preferred_date);
    expect(fields().budget).toHaveValue(draft.budget_band);
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ ...draft, category });
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("restores through sign-in without automatically posting, then sends the unchanged API contract on explicit submit", async () => {
    localStorage.setItem(key, JSON.stringify(draft));
    const view = render(ui());
    expect(screen.getByRole("link", { name: messages.postJob.authCta })).toHaveAttribute(
      "href",
      "/en/login?next=/en/services/post-job",
    );
    mocks.session = { access_token: "token" };
    view.rerender(ui());
    expect(mocks.request).not.toHaveBeenCalled();
    mocks.request.mockResolvedValue({ job: { id: "job-1" } });
    submit(view.container);
    await screen.findByRole("status");
    expect(mocks.request).toHaveBeenCalledExactlyOnceWith("/jobs", {
      method: "POST",
      body: JSON.stringify({ ...draft, photo_paths: [] }),
    });
    expect(localStorage.getItem(key)).toBeNull();
  });

  it.each([false, true])(
    "keeps a successful POST truthful when removal fails (no_match=%s)",
    async (noMatch) => {
      localStorage.setItem(key, JSON.stringify(draft));
      mocks.session = { access_token: "token" };
      vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
        throw new DOMException("Denied", "SecurityError");
      });
      mocks.request.mockResolvedValue({ job: { id: "job-1", broadcast: { no_match: noMatch } } });
      const view = render(ui());
      submit(view.container);
      expect(await screen.findByRole("status")).toHaveTextContent(
        noMatch ? messages.postJob.ack.noMatch : messages.postJob.ack.sent,
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      submit(view.container);
      expect(mocks.request).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: messages.postJob.submit })).toBeDisabled();
    },
  );

  it("blocks concurrent submits and permits explicit retry after a request failure", async () => {
    mocks.session = { access_token: "token" };
    localStorage.setItem(key, JSON.stringify(draft));
    const pending = deferred();
    const view = render(ui());
    act(() => {
      submit(view.container);
      submit(view.container);
    });
    expect(mocks.request).toHaveBeenCalledTimes(1);
    await act(async () => pending.reject(new Error("Offline")));
    expect(screen.getByRole("alert")).toHaveTextContent(messages.postJob.errors.generic);
    expect(fields().description).toHaveValue(draft.description);
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual(draft);
    mocks.request.mockResolvedValue({ job: { id: "job-2" } });
    submit(view.container);
    await screen.findByRole("status");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledTimes(2);
  });

  it("does not persist or send work after a guest unmounts", () => {
    const write = vi.spyOn(Storage.prototype, "setItem");
    const view = render(ui());
    fill();
    const calls = write.mock.calls.length;
    view.unmount();
    expect(write).toHaveBeenCalledTimes(calls);
    expect(mocks.request).not.toHaveBeenCalled();
    render(ui());
    expect(fields().description).toHaveValue(draft.description);
  });

  it("does not delete a newer draft when a pending POST resolves after navigation", async () => {
    mocks.session = { access_token: "token" };
    localStorage.setItem(key, JSON.stringify(draft));
    const pending = deferred();
    const view = render(ui());
    submit(view.container);
    view.unmount();
    const newer = { ...draft, description: "Another job for tomorrow" };
    localStorage.setItem(key, JSON.stringify(newer));
    await act(async () => pending.resolve({ job: { id: "job-1" } }));
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual(newer);
    expect(mocks.request).toHaveBeenCalledTimes(1);
  });
  it("validates required input without creating a job", () => {
    mocks.session = { access_token: "token" };
    const view = render(ui());
    submit(view.container);
    expect(screen.getByRole("alert")).toHaveTextContent(messages.postJob.errors.required);
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("posts explicitly with denied storage and retains trim/null payload semantics", async () => {
    mocks.session = { access_token: "token" };
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("Denied", "SecurityError");
    });
    mocks.request.mockResolvedValue({ job: { id: "job-1" } });
    const view = render(ui());
    fireEvent.change(fields().description, { target: { value: "  Fix the leaking tap  " } });
    fireEvent.change(fields().area, { target: { value: "  Lusaka  " } });
    expect(mocks.request).not.toHaveBeenCalled();
    submit(view.container);
    expect(await screen.findByRole("status")).toHaveTextContent(messages.postJob.ack.sent);
    expect(mocks.request).toHaveBeenCalledExactlyOnceWith("/jobs", {
      method: "POST",
      body: JSON.stringify({
        category: "home_services",
        description: "Fix the leaking tap",
        service_area: "Lusaka",
        preferred_date: null,
        budget_band: "flexible",
        photo_paths: [],
      }),
    });
  });

  it("preserves restoration while the session loads and never posts on session resolution", () => {
    localStorage.setItem(key, JSON.stringify(draft));
    mocks.loading = true;
    const view = render(ui());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    mocks.loading = false;
    mocks.session = { access_token: "token" };
    view.rerender(ui());
    expect(fields().description).toHaveValue(draft.description);
    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("does not recreate a cleared draft after success or session loss", async () => {
    mocks.session = { access_token: "token" };
    localStorage.setItem(key, JSON.stringify(draft));
    mocks.request.mockResolvedValue({ job: { id: "job-1" } });
    const view = render(ui());
    submit(view.container);
    await screen.findByRole("status");
    mocks.session = null;
    view.rerender(ui());
    expect(localStorage.getItem(key)).toBeNull();
    expect(screen.queryByText(messages.postJob.draftSaved)).not.toBeInTheDocument();
    submit(view.container);
    expect(mocks.request).toHaveBeenCalledTimes(1);
  });
});
