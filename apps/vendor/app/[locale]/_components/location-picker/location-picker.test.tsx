// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../../../packages/i18n/messages/en/vendor.json";

vi.mock("../../listings/new/_lib/ui", () => ({
  Button: ({
    children,
    loading,
    loadingLabel: _loadingLabel,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    loading?: boolean;
    loadingLabel?: string;
  }) => (
    <button type="button" {...props} disabled={props.disabled || loading}>
      {children}
    </button>
  ),
  FormField: ({ label, children }: { label: string; children: React.ReactNode }) => (
    <label>
      {label}
      {children}
    </label>
  ),
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    code: string;
    details: Record<string, unknown>;
    constructor(code: string, details: Record<string, unknown> = {}) {
      super(code);
      this.code = code;
      this.details = details;
    }
  },
}));

import { LocationPicker } from "./location-picker";

vi.mock("./location-picker-map", () => ({
  LUSAKA_CENTER: { lat: -15.4167, lng: 28.2833 },
  LocationPickerMap: ({ onPinMove }: { onPinMove: (lat: number, lng: number) => void }) => (
    <button type="button" onClick={() => onPinMove(-15.5, 28.31)}>
      move-pin
    </button>
  ),
}));

const searchMock = vi.fn();

vi.mock("./geo-client", () => ({
  createGeoClient: () => ({
    search: (...args: unknown[]) => searchMock(...args),
  }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  searchMock.mockReset();
});

function renderPicker(onChange = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={{ vendor: en }}>
      <LocationPicker
        value={{ lat: "", lng: "", landmark: "" }}
        onChange={onChange}
        getToken={() => "token"}
      />
    </NextIntlClientProvider>,
  );
  return onChange;
}

describe("LocationPicker", () => {
  beforeEach(() => {
    searchMock.mockResolvedValue([{ label: "Arcades, Lusaka", lat: -15.42, lng: 28.28 }]);
  });

  it("fills lat/lng from mocked geolocation", async () => {
    const onChange = renderPicker();
    const position = {
      coords: { latitude: -15.4167, longitude: 28.2833, accuracy: 12 },
    };
    vi.stubGlobal("navigator", {
      geolocation: {
        getCurrentPosition: (success: (value: typeof position) => void) => success(position),
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "Use my current location" }));

    await waitFor(() => {
      const last = onChange.mock.calls.at(-1)?.[0] as { lat: string; lng: string };
      expect(last.lat).toBe("-15.416700");
      expect(last.lng).toBe("28.283300");
    });
  });

  it("shows fallback message when geolocation permission is denied", () => {
    renderPicker();
    vi.stubGlobal("navigator", {
      geolocation: {
        getCurrentPosition: (_success: unknown, error: (value: { code: number }) => void) =>
          error({ code: 1 }),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Use my current location" }));
    expect(
      screen.getByText(
        "Location access was denied. Search for a place or drag the pin on the map instead.",
      ),
    ).toBeInTheDocument();
  });

  it("moves the pin when a search result is picked", async () => {
    const onChange = renderPicker();
    fireEvent.change(screen.getByPlaceholderText("e.g. Arcades, Lusaka"), {
      target: { value: "Arcades" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Arcades, Lusaka");
    fireEvent.click(screen.getByText("Arcades, Lusaka"));
    const last = onChange.mock.calls.at(-1)?.[0] as { lat: string; lng: string };
    expect(last.lat).toBe("-15.420000");
    expect(last.lng).toBe("28.280000");
  });
});
