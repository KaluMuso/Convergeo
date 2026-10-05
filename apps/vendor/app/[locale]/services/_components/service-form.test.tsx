import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../packages/i18n/messages/en/services.json";
import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { ServiceForm } from "./service-form";

import type { ServiceSummary } from "../_lib/services-client";

const { createService, updateService, push, refresh, auth } = vi.hoisted(() => ({
  createService: vi.fn(),
  updateService: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
  auth: {
    session: { access_token: "test-token", user: { id: "vendor-1" } } as {
      access_token: string;
      user: { id: string };
    } | null,
  },
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: auth.session,
    loading: false,
  }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
vi.mock("../_lib/services-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../_lib/services-client")>()),
  createServicesClient: () => ({ createService, updateService }),
}));

const labels = servicesMessages.vendor.form;
const errors = servicesMessages.vendor.errors;
const messages = {
  services: { vendor: servicesMessages.vendor, categories: servicesMessages.categories },
  vendor: { listings: { fields: { priceInvalid: vendorMessages.listings.fields.priceInvalid } } },
};

function editService(id: string, title: string, fromPriceNgwee: number | null): ServiceSummary {
  return {
    id,
    slug: id,
    title,
    category: "home-services",
    description: null,
    service_area: null,
    from_price_ngwee: fromPriceNgwee,
    bookable: false,
    booking_price_ngwee: null,
    status: "draft",
    portfolio_images: [],
    includes: [],
  };
}

function mount(mode: "create" | "edit" = "create", initialFromPriceNgwee: number | null = null) {
  const view = render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm
        locale="en"
        mode={mode}
        serviceId={mode === "edit" ? "service-1" : undefined}
        initialService={
          mode === "edit"
            ? editService("service-1", "Test service", initialFromPriceNgwee)
            : undefined
        }
      />
    </NextIntlClientProvider>,
  );
  if (mode === "create") {
    fireEvent.change(screen.getByLabelText(labels.titleLabel), {
      target: { value: "Test service" },
    });
  }
  return view;
}

function enterFromPrice(value: string) {
  fireEvent.change(screen.getByLabelText(labels.fromPriceLabel), {
    target: { value },
  });
}

function enableBooking(value: string) {
  fireEvent.click(screen.getByRole("checkbox", { name: new RegExp(labels.bookableLabel) }));
  fireEvent.change(screen.getByLabelText(labels.bookingPriceLabel), {
    target: { value },
  });
}

beforeEach(() => {
  auth.session = { access_token: "test-token", user: { id: "vendor-1" } };
  createService.mockResolvedValue({ service: {} });
  updateService.mockResolvedValue({ service: {} });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("creates a published service with exact grouped and decimal prices", async () => {
  mount();
  enterFromPrice("1,000.01");
  enableBooking("12.34");
  fireEvent.click(screen.getByRole("button", { name: labels.publish }));
  await waitFor(() => expect(createService).toHaveBeenCalledOnce());
  expect(createService.mock.calls[0]?.[0]).toMatchObject({
    from_price_ngwee: 100_001,
    booking_price_ngwee: 1_234,
    bookable: true,
    status: "active",
  });
});

it("keeps an empty optional from price null on create", async () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  await waitFor(() => expect(createService).toHaveBeenCalledOnce());
  expect(createService.mock.calls[0]?.[0]).toMatchObject({
    from_price_ngwee: null,
  });
});

it.each(["12abc", "1e3", "1.234", "Infinity", "90071992547409.92", "-1"])(
  "rejects malformed optional from price %s before create or publish",
  (value) => {
    mount();
    enterFromPrice(value);
    fireEvent.click(screen.getByRole("button", { name: labels.publish }));
    expect(screen.getByText(vendorMessages.listings.fields.priceInvalid)).toBeVisible();
    expect(createService).not.toHaveBeenCalled();
  },
);

it.each(["12abc", "1e3", "1.234", "Infinity", "90071992547409.92", "0", ""])(
  "rejects malformed or missing booking price %s before publish",
  (value) => {
    mount();
    enableBooking(value);
    fireEvent.click(screen.getByRole("button", { name: labels.publish }));
    expect(screen.getByText(errors.bookablePrice)).toBeVisible();
    expect(createService).not.toHaveBeenCalled();
  },
);

it("uses exact ngwee prices in the edit payload", async () => {
  mount("edit");
  enterFromPrice("1,000.01");
  enableBooking("0.29");
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  await waitFor(() => expect(updateService).toHaveBeenCalledOnce());
  expect(updateService.mock.calls[0]?.[0]).toBe("service-1");
  expect(updateService.mock.calls[0]?.[1]).toMatchObject({
    from_price_ngwee: 100_001,
    booking_price_ngwee: 29,
    status: "draft",
  });
});

it("preserves a safe integer ngwee price when an edit form loads and saves unchanged", async () => {
  mount("edit", Number.MAX_SAFE_INTEGER);
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  await waitFor(() => expect(updateService).toHaveBeenCalledOnce());
  expect(updateService.mock.calls[0]?.[1]).toMatchObject({
    from_price_ngwee: Number.MAX_SAFE_INTEGER,
  });
});

it("rejects malformed prices before edit save", () => {
  mount("edit");
  enterFromPrice("12abc");
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  expect(screen.getByText(vendorMessages.listings.fields.priceInvalid)).toBeVisible();
  expect(updateService).not.toHaveBeenCalled();
});

it("shows the newly selected service when edit props change", () => {
  const view = mount("edit");
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm
        locale="en"
        mode="edit"
        serviceId="service-2"
        initialService={editService("service-2", "Other service", 2500)}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByLabelText(labels.titleLabel)).toHaveValue("Other service");
  expect(screen.getByLabelText(labels.fromPriceLabel)).toHaveValue("25.00");
});

it("waits for the matching record before exposing a newly selected service for editing", () => {
  const view = mount("edit");
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm
        locale="en"
        mode="edit"
        serviceId="service-2"
        initialService={editService("service-1", "Test service", null)}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.queryByLabelText(labels.titleLabel)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: labels.save })).not.toBeInTheDocument();
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm
        locale="en"
        mode="edit"
        serviceId="service-2"
        initialService={editService("service-2", "Other service", 2500)}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByLabelText(labels.titleLabel)).toHaveValue("Other service");
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  expect(updateService).toHaveBeenCalledWith(
    "service-2",
    expect.objectContaining({ title: "Other service", from_price_ngwee: 2500 }),
  );
});

it("does not navigate when an old service save finishes after the service changes", async () => {
  let completeSave!: (value: { service: object }) => void;
  updateService.mockReturnValueOnce(
    new Promise((resolve) => {
      completeSave = resolve;
    }),
  );
  const view = mount("edit");
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  expect(updateService).toHaveBeenCalledOnce();
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm
        locale="en"
        mode="edit"
        serviceId="service-2"
        initialService={editService("service-2", "Other service", 2500)}
      />
    </NextIntlClientProvider>,
  );
  await act(async () => completeSave({ service: {} }));
  expect(push).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

it("does not navigate when the vendor signs out while a save is pending", async () => {
  let completeSave!: (value: { service: object }) => void;
  createService.mockReturnValueOnce(
    new Promise((resolve) => {
      completeSave = resolve;
    }),
  );
  const view = mount();
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  expect(createService).toHaveBeenCalledOnce();
  auth.session = null;
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm locale="en" mode="create" />
    </NextIntlClientProvider>,
  );
  expect(screen.getByText(errors.authRequired)).toBeVisible();
  await act(async () => completeSave({ service: {} }));
  expect(push).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

it("keeps one save in flight when submit controls are clicked again", async () => {
  let completeSave!: (value: { service: object }) => void;
  createService.mockReturnValueOnce(
    new Promise((resolve) => {
      completeSave = resolve;
    }),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  for (const button of screen.getAllByRole("button", { name: labels.saving })) {
    expect(button).toBeDisabled();
    fireEvent.click(button);
  }
  expect(createService).toHaveBeenCalledOnce();
  await act(async () => completeSave({ service: {} }));
});

it("allows a pending save to finish after a token refresh for the same vendor", async () => {
  let completeSave!: (value: { service: object }) => void;
  createService.mockReturnValueOnce(
    new Promise((resolve) => {
      completeSave = resolve;
    }),
  );
  const view = mount();
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  auth.session = { access_token: "renewed-token", user: { id: "vendor-1" } };
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm locale="en" mode="create" />
    </NextIntlClientProvider>,
  );
  await act(async () => completeSave({ service: {} }));
  expect(createService).toHaveBeenCalledOnce();
  expect(push).toHaveBeenCalledWith("/en/services");
  expect(refresh).toHaveBeenCalledOnce();
});

it("discards an old save after sign-out even if the same vendor signs in again", async () => {
  let completeSave!: (value: { service: object }) => void;
  createService.mockReturnValueOnce(
    new Promise((resolve) => {
      completeSave = resolve;
    }),
  );
  const view = mount();
  fireEvent.click(screen.getByRole("button", { name: labels.save }));
  auth.session = null;
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm locale="en" mode="create" />
    </NextIntlClientProvider>,
  );
  auth.session = { access_token: "new-session", user: { id: "vendor-1" } };
  view.rerender(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ServiceForm locale="en" mode="create" />
    </NextIntlClientProvider>,
  );
  await act(async () => completeSave({ service: {} }));
  expect(push).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});
