import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
  auth: {
    session: { user: { id: "buyer-a" }, access_token: "token-a" },
    generation: 1,
    loading: false,
    error: null,
  },
}));
vi.mock("../../../../../../lib/customer-session", () => ({
  useSession: () => mocks.auth,
  customerAuth: { snapshot: () => mocks.auth },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@vergeo/config", () => ({
  ApiError: class extends Error {},
  createApiClient: ({ getToken }: { getToken: () => string | null }) => ({
    request: (path: string, options: unknown) => mocks.request(path, options, getToken()),
  }),
}));

import { BookService } from "./book-service";

const jobId = "10000000-0000-4000-8000-000000000001";
const response = {
  job_id: jobId,
  checkout_group_id: "group-a",
  deposit_ngwee: 30000,
  balance_ngwee: 70000,
  total_job_ngwee: 100000,
};
function flow() {
  return <BookService locale="en" serviceId="service-a" priceNgwee={100000} />;
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  mocks.auth.generation = 1;
  mocks.auth.session = { user: { id: "buyer-a" }, access_token: "token-a" };
});

it("hands the authorized booking job to its funding surface", async () => {
  mocks.request.mockResolvedValue(response);
  render(flow());
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(mocks.push).toHaveBeenCalledWith(`/en/account/jobs/${jobId}`));
  expect(mocks.request).toHaveBeenCalledTimes(1);
});

it("keeps a single booking in flight and suppresses an ABA account completion", async () => {
  let resolve!: (value: typeof response) => void;
  mocks.request.mockReturnValue(
    new Promise((res) => {
      resolve = res;
    }),
  );
  const view = render(flow());
  fireEvent.click(screen.getByRole("button"));
  fireEvent.click(screen.getByRole("button"));
  expect(mocks.request).toHaveBeenCalledTimes(1);
  mocks.auth.generation = 3;
  view.rerender(flow());
  await act(async () => resolve(response));
  expect(mocks.push).not.toHaveBeenCalled();
});

it("does not use a checkout group when a booking lacks its job identity", async () => {
  mocks.request.mockResolvedValue({ ...response, job_id: undefined });
  render(flow());
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByText("errors.generic")).toBeTruthy());
  expect(mocks.push).not.toHaveBeenCalled();
});
