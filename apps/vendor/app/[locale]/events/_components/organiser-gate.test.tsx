import { cleanup, render, screen } from "@testing-library/react";
import { ApiError } from "@vergeo/config";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it } from "vitest";

import vendor from "../../../../../../packages/i18n/messages/en/vendor.json";
import { isNotOrganiserError } from "../_lib/organiser-gate";

import { OrganiserGate } from "./organiser-gate";

afterEach(cleanup);

it("offers both routes and a coming-soon collaboration stub", () => {
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor }}>
      <OrganiserGate locale="en" />
    </NextIntlClientProvider>,
  );
  const become = screen.getByTestId("organiser-gate-become");
  expect(become.getAttribute("href")).toBe("/en/onboarding/status");
  expect(become.textContent).toBe("Become an organiser");
  expect(screen.getByText("Run an event with a verified organiser")).toBeTruthy();
  const collaborate = screen.getByTestId("organiser-gate-collaborate") as HTMLButtonElement;
  expect(collaborate.disabled).toBe(true);
  expect(screen.getByText(/Coming soon/)).toBeTruthy();
});

it("treats 403 kyc_required and forbidden as not-an-organiser, not a load failure", () => {
  expect(isNotOrganiserError(new ApiError("kyc_required", "x", { status: 403 }))).toBe(true);
  expect(isNotOrganiserError(new ApiError("forbidden", "x", { status: 403 }))).toBe(true);
  expect(isNotOrganiserError(new ApiError("internal_error", "x", { status: 500 }))).toBe(false);
  expect(isNotOrganiserError(new ApiError("forbidden", "x", { status: 401 }))).toBe(false);
  expect(isNotOrganiserError(new Error("network"))).toBe(false);
});
