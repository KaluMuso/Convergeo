import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import servicesMessages from "../../../../../../packages/i18n/messages/en/services.json";
import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { ServiceForm } from "./service-form";

const { createService, updateService, push, refresh } = vi.hoisted(() => ({
  createService: vi.fn(),
  updateService: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@vergeo/auth/use-session", () => ({
  useSession: () => ({
    session: { access_token: "test-token" },
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

function mount(mode: "create" | "edit" = "create", initialFromPriceNgwee: number | null = null) {
  render(
    <NextIntlClientProvider
      locale="en"
      messages={{
        services: {
          vendor: servicesMessages.vendor,
          categories: servicesMessages.categories,
        },
        vendor: {
          listings: {
            fields: {
              priceInvalid: vendorMessages.listings.fields.priceInvalid,
            },
          },
        },
      }}
    >
      <ServiceForm
        locale="en"
        mode={mode}
        serviceId={mode === "edit" ? "service-1" : undefined}
        initialService={
          mode === "edit"
            ? {
                id: "service-1",
                slug: "test-service",
                title: "Test service",
                category: "home-services",
                description: null,
                service_area: null,
                from_price_ngwee: initialFromPriceNgwee,
                bookable: false,
                booking_price_ngwee: null,
                status: "draft",
                portfolio_images: [],
                includes: [],
              }
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
