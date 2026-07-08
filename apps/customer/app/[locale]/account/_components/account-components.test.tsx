// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const request = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

vi.mock("./account-api", () => ({
  createAccountApiClient: () => ({
    patchProfile: request,
    createAddress: request,
    patchAddress: request,
    listAddresses: vi.fn().mockResolvedValue([]),
    deleteAddress: vi.fn(),
    patchPreferences: request,
    getPreferences: vi.fn(),
    getProfile: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { AddressForm } from "./address-form";
import { ProfileForm } from "./profile-form";

const addressLabels = {
  label: "Label",
  labelPlaceholder: "Home",
  landmark: "Landmark",
  landmarkPlaceholder: "Near mall",
  landmarkHelp: "Help",
  phone: "Phone",
  phonePlaceholder: "97 123 4567",
  latitude: "Latitude",
  longitude: "Longitude",
  coordsHelp: "Coords help",
  useGps: "Use my location",
  gpsLoading: "Finding location…",
  gpsDenied: "Location access was denied. Enter coordinates manually below.",
  gpsUnavailable: "Geolocation is not available on this device.",
  mapPreview: "Location preview",
  mapAlt: "Map preview near {lat}, {lng}",
  mapEmpty: "No coordinates yet",
  coordsTemplate: "{lat}, {lng}",
  save: "Save address",
  saving: "Saving…",
  cancel: "Cancel",
  requiredLandmark: "Landmark directions are required.",
  error: "Could not save address.",
  required: "Required",
};

const profileLabels = {
  nameLabel: "Display name",
  namePlaceholder: "Your name",
  localeLabel: "Language",
  phoneLabel: "Phone",
  phoneHelp: "Verified number",
  save: "Save changes",
  saving: "Saving…",
  updated: "Profile updated for {name}",
  error: "Could not save profile",
  locales: { en: "English", bem: "Bemba", nya: "Nyanja", fr: "French" },
};

describe("AddressForm geolocation fallback", () => {
  beforeEach(() => {
    Object.defineProperty(global.navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (_success: PositionCallback, error: PositionErrorCallback) => {
          error({ code: 1, message: "denied", PERMISSION_DENIED: 1 } as GeolocationPositionError);
        },
      },
    });
  });

  it("shows manual-entry fallback when geolocation is denied", async () => {
    const user = userEvent.setup();
    render(
      <AddressForm
        locale="en"
        accessToken="token"
        labels={addressLabels}
        onCancel={() => undefined}
        onSaved={() => undefined}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Use my location" }));

    expect(
      await screen.findByText("Location access was denied. Enter coordinates manually below."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    expect(screen.getByLabelText("Longitude")).toBeInTheDocument();
  });
});

describe("account i18n", () => {
  it("loads nested account namespace keys including privacy section", async () => {
    const { loadNamespace, clearMessageCache } = await import("@vergeo/i18n");
    clearMessageCache();
    const messages = (await loadNamespace("en", "account")) as {
      title: string;
      nav: { profile: string; privacy: string };
      privacy: Record<string, string>;
      addresses: { useGps: string };
    };
    expect(messages.title).toBe("My account");
    expect(messages.nav).toMatchObject({
      profile: expect.any(String),
      privacy: expect.any(String),
    });
    expect(messages.privacy).toMatchObject({
      title: expect.any(String),
      exportCta: expect.any(String),
      deleteCta: expect.any(String),
      exportConfirmBody: expect.any(String),
      deleteConfirmBody: expect.any(String),
      retentionNote: expect.any(String),
    });
    expect(messages.addresses.useGps).toBe("Use my location");
  });
});
describe("ProfileForm locale switch", () => {
  it("navigates to the new locale prefix after saving", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign },
    });

    request.mockResolvedValue({
      id: "user-1",
      phone: "+260971234567",
      display_name: "Chisomo",
      locale: "bem",
    });

    const user = userEvent.setup();
    render(
      <ProfileForm
        locale="en"
        accessToken="token"
        initialProfile={{
          id: "user-1",
          phone: "+260971234567",
          display_name: "Chisomo",
          locale: "en",
        }}
        labels={profileLabels}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Language"), "bem");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith("/bem/account");
    });
  });
});
