import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ServiceEditView } from "./service-edit-view";

import type { ServiceSummary } from "../../../_lib/services-client";

const { auth, listServices, translate } = vi.hoisted(() => ({
  auth: {
    session: { access_token: "token-a", user: { id: "vendor-a" } } as {
      access_token: string;
      user: { id: string };
    } | null,
    loading: false,
  },
  listServices: vi.fn(),
  translate: (key: string) => key,
}));

vi.mock("@vergeo/auth/use-session", () => ({ useSession: () => auth }));
vi.mock("next-intl", () => ({ useTranslations: () => translate }));
vi.mock("../../../_lib/services-client", () => ({
  createServicesClient: () => ({ listServices }),
}));
vi.mock("../../../_lib/ui", () => ({
  Spinner: ({ label }: { label: string }) => <p data-testid="loading">{label}</p>,
}));
vi.mock("../../../_components/service-form", () => ({
  ServiceForm: ({
    serviceId,
    initialService,
  }: {
    serviceId: string;
    initialService: ServiceSummary;
  }) => <p data-testid="service-form">{`${serviceId}:${initialService.title}`}</p>,
}));

function service(id: string, title: string): ServiceSummary {
  return {
    id,
    slug: id,
    title,
    category: "home-services",
    description: null,
    service_area: null,
    from_price_ngwee: null,
    bookable: false,
    booking_price_ngwee: null,
    status: "draft",
    portfolio_images: [],
    includes: [],
  };
}

function mount(serviceId: string) {
  return render(<ServiceEditView locale="en" serviceId={serviceId} />);
}

beforeEach(() => {
  auth.session = { access_token: "token-a", user: { id: "vendor-a" } };
  auth.loading = false;
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("clears a failed lookup when navigation reaches a valid service", async () => {
  listServices
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValueOnce({ items: [service("service-b", "Second service")] });
  const view = mount("missing-service");
  expect(await screen.findByText("vendor.errors.loadFailed")).toBeVisible();
  view.rerender(<ServiceEditView locale="en" serviceId="service-b" />);
  expect(screen.getByTestId("loading")).toBeVisible();
  await waitFor(() => expect(listServices).toHaveBeenCalledTimes(2));
  expect(await screen.findByTestId("service-form")).toHaveTextContent("service-b:Second service");
});

it("hides the previous vendor's record as soon as the account changes", async () => {
  let finishSecond!: (value: { items: ServiceSummary[] }) => void;
  listServices
    .mockResolvedValueOnce({ items: [service("shared-id", "Vendor A record")] })
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishSecond = resolve;
      }),
    );
  const view = mount("shared-id");
  expect(await screen.findByTestId("service-form")).toHaveTextContent("Vendor A record");
  auth.session = { access_token: "token-b", user: { id: "vendor-b" } };
  view.rerender(<ServiceEditView locale="en" serviceId="shared-id" />);
  expect(screen.queryByTestId("service-form")).not.toBeInTheDocument();
  expect(screen.getByTestId("loading")).toBeVisible();
  await act(async () => finishSecond({ items: [service("shared-id", "Vendor B record")] }));
  expect(screen.getByTestId("service-form")).toHaveTextContent("Vendor B record");
});

it("ignores an earlier lookup that settles after switching services", async () => {
  let finishFirst!: (value: { items: ServiceSummary[] }) => void;
  listServices
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishFirst = resolve;
      }),
    )
    .mockResolvedValueOnce({ items: [service("service-b", "Second service")] });
  const view = mount("service-a");
  view.rerender(<ServiceEditView locale="en" serviceId="service-b" />);
  expect(await screen.findByTestId("service-form")).toHaveTextContent("service-b:Second service");
  await act(async () => finishFirst({ items: [service("service-a", "First service")] }));
  expect(screen.getByTestId("service-form")).toHaveTextContent("service-b:Second service");
});

it("keeps a pending lookup hidden after sign-out", async () => {
  let finishLookup!: (value: { items: ServiceSummary[] }) => void;
  listServices.mockReturnValueOnce(
    new Promise((resolve) => {
      finishLookup = resolve;
    }),
  );
  const view = mount("service-a");
  auth.session = null;
  view.rerender(<ServiceEditView locale="en" serviceId="service-a" />);
  expect(screen.getByText("vendor.errors.authRequired")).toBeVisible();
  await act(async () => finishLookup({ items: [service("service-a", "Old record")] }));
  expect(screen.queryByTestId("service-form")).not.toBeInTheDocument();
});

it("ignores an earlier vendor's response after an account change", async () => {
  let finishFirst!: (value: { items: ServiceSummary[] }) => void;
  listServices
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishFirst = resolve;
      }),
    )
    .mockResolvedValueOnce({ items: [service("shared-id", "Vendor B record")] });
  const view = mount("shared-id");
  auth.session = { access_token: "token-b", user: { id: "vendor-b" } };
  view.rerender(<ServiceEditView locale="en" serviceId="shared-id" />);
  expect(await screen.findByTestId("service-form")).toHaveTextContent("Vendor B record");
  await act(async () => finishFirst({ items: [service("shared-id", "Vendor A record")] }));
  expect(screen.getByTestId("service-form")).toHaveTextContent("Vendor B record");
});
