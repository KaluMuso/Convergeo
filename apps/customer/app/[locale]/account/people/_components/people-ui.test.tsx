import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import socialMessages from "../../../../../../../packages/i18n/messages/en/social.json";

import { AddPeoplePanel } from "./add-people-panel";

const supportsContactPicker = vi.fn(() => false);

vi.mock("../../../../../lib/social/phone", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../../../lib/social/phone")>();
  return {
    ...actual,
    supportsContactPicker: (...args: Parameters<typeof actual.supportsContactPicker>) =>
      supportsContactPicker(...args),
  };
});

vi.mock("../../../../../lib/social/contacts-api", () => ({
  contactsApi: {
    getPhoneDiscovery: vi.fn().mockResolvedValue({ enabled: false, pepper_configured: true }),
    getQr: vi.fn().mockResolvedValue({ handle: "demo", payload: "vgo:add:demo" }),
    sendRequest: vi.fn(),
    discoverHashes: vi.fn().mockResolvedValue({ items: [] }),
    setPhoneDiscovery: vi.fn(),
  },
}));

describe("AddPeoplePanel", () => {
  afterEach(() => {
    cleanup();
    supportsContactPicker.mockReset();
    supportsContactPicker.mockReturnValue(false);
  });

  it("shows Contact Picker button only when supported", () => {
    supportsContactPicker.mockReturnValue(true);
    render(
      <NextIntlClientProvider locale="en" messages={{ social: socialMessages }}>
        <AddPeoplePanel locale="en" siteOrigin="https://www.vergeo5.com" />
      </NextIntlClientProvider>,
    );
    expect(screen.getByTestId("contact-picker-button")).toBeInTheDocument();
    expect(screen.queryByTestId("share-fallback")).not.toBeInTheDocument();
  });

  it("shows share fallback with wa.me when Contact Picker is unsupported", () => {
    supportsContactPicker.mockReturnValue(false);
    render(
      <NextIntlClientProvider locale="en" messages={{ social: socialMessages }}>
        <AddPeoplePanel locale="en" siteOrigin="https://www.vergeo5.com" />
      </NextIntlClientProvider>,
    );
    expect(screen.getByTestId("share-fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("contact-picker-button")).not.toBeInTheDocument();
    const invite = screen.getByRole("link", { name: socialMessages.add.inviteWhatsApp });
    expect(invite.getAttribute("href")).toMatch(/^https:\/\/wa\.me\/\?text=/);
  });
});
